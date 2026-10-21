"""
Apps Module.

Represents / handles all Home Assistant app specific logic
"""

from __future__ import annotations

import contextlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfile, copytree, rmtree
from typing import TYPE_CHECKING, Any

import emoji
import semver
import yaml
from github.GithubException import GithubException, UnknownObjectException
from jinja2 import BaseLoader, Environment

from .const import CHANNEL_BETA, CHANNEL_EDGE, CONFIG_FILENAMES, DEFAULT_ARCHS
from .exceptions import AppConfigNotFoundError, AppNotUpdatingError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from git import Repo
    from github.Commit import Commit
    from github.GitRelease import GitRelease
    from github.Repository import Repository as GitHubRepository

    from .github import GitHub
    from .output import Output

STATIC_FILES = (
    "logo.png",
    "icon.png",
    "README.md",
    "DOCS.md",
    "apparmor.txt",
    "translations",
)


@dataclass(frozen=True)
class AppConfig:
    """Configuration of a single app, as declared in a repository app list."""

    # Directory holding this app inside the apps repository.
    repository_target: str
    image: str
    # The "org/repo" that holds the app's own source.
    repository: str
    # Directory holding this app inside its own repository.
    app_target: str
    channel: str

    @classmethod
    def from_app_list(
        cls,
        target: str,
        config: dict[str, Any],
        channel: str,
    ) -> AppConfig:
        """Create configuration from a single entry in a repository app list."""
        return cls(
            repository_target=target,
            image=config["image"],
            repository=config["repository"],
            app_target=config["target"],
            channel=channel,
        )


class App:
    """Object representing an Home Assistant app."""

    app_repository: GitHubRepository | None
    app_clone: Repo | None
    clone_dir: Path | None

    current_version: str | None
    current_commit: Commit | None
    current_release: GitRelease | None
    existing_config_filename: str | None

    latest_version: str | None
    latest_commit: Commit | None
    latest_release: GitRelease | None
    latest_is_release: bool

    archs: Sequence[str]
    name: str
    description: str
    slug: str
    url: str

    def __init__(
        self,
        github: GitHub,
        repository_dir: Path,
        config: AppConfig,
        *,
        updating: bool,
        output: Output,
    ) -> None:
        """Initialize a new Home Assistant app object."""
        self.github = github
        self.repository_dir = repository_dir
        self.config = config
        self.updating = updating
        self.output = output

        self.app_repository = None
        self.app_clone = None
        self.clone_dir = None

        self.current_version = None
        self.current_commit = None
        self.current_release = None
        self.existing_config_filename = None

        self.latest_version = None
        self.latest_commit = None
        self.latest_release = None
        self.latest_is_release = True

        self.archs = DEFAULT_ARCHS

    @property
    def target_dir(self) -> Path:
        """Return this app's directory inside the apps repository."""
        return self.repository_dir / self.config.repository_target

    @property
    def source_dir(self) -> Path:
        """Return this app's directory inside its own cloned repository."""
        return Path(self.app_clone.working_dir) / self.config.app_target

    def load(self) -> None:
        """Load the current and latest available state of this app."""
        self.app_repository = self.github.get_repo(self.config.repository)
        self.output.info(
            f"Loading app information from: {self.app_repository.html_url}"
        )

        self._load_current_info()

        if not self.updating:
            return

        self._load_latest_info()

        if self.needs_update(force=False):
            self.output.warning("This app has an update waiting to be published!")
        else:
            self.output.success("This app is up to date.")

    def clone_repository(self) -> None:
        """Clone the app source to a local working directory."""
        self.output.step("Cloning app git repository")
        self.clone_dir = Path(tempfile.mkdtemp(prefix=self.config.app_target))
        self.app_clone = self.github.clone(self.app_repository, str(self.clone_dir))
        self.app_clone.git.checkout(self.current_commit.sha)
        self.output.done("Cloned!")

    def cleanup(self) -> None:
        """Remove the temporary clone of this app's own repository."""
        if self.clone_dir is None:
            return

        rmtree(self.clone_dir, ignore_errors=True)
        self.clone_dir = None

    def update(self) -> None:
        """Update this app inside the given app repository."""
        if not self.updating:
            raise AppNotUpdatingError(self.config.repository_target)

        self.current_version = self.latest_version
        self.current_release = self.latest_release
        self.current_commit = self.latest_commit

        self.clone_repository()
        self.ensure_app_dir()
        self.generate_app_config()
        self.update_static_files()
        self.generate_readme()
        self.generate_app_changelog()

    def _load_current_info(self) -> None:
        """Load current app version information and current config."""
        self.existing_config_filename = next(
            (name for name in CONFIG_FILENAMES if (self.target_dir / name).is_file()),
            None,
        )

        if self.existing_config_filename is None:
            self.output.info(
                f"Current version: {self.output.emphasis('Not available')}"
            )
            return

        with (self.target_dir / self.existing_config_filename).open(
            encoding="utf8"
        ) as f:
            current_config = (
                json.load(f)
                if self.existing_config_filename.endswith(".json")
                else yaml.safe_load(f)
            )

        self._apply_config(current_config)
        self.current_version = current_config["version"]

        current_parsed_version = False
        with contextlib.suppress(ValueError):
            current_parsed_version = semver.parse(self.current_version)

        if current_parsed_version:
            try:
                ref = self.app_repository.get_git_ref("tags/" + self.current_version)
            except UnknownObjectException:
                ref = self.app_repository.get_git_ref("tags/v" + self.current_version)
            self.current_commit = self.app_repository.get_commit(ref.object.sha)
        else:
            try:
                self.current_commit = self.app_repository.get_commit(
                    f"v{self.current_version}"
                )
            except GithubException:
                self.current_commit = self.app_repository.get_commit(
                    self.current_version
                )

        self.output.info(
            f"Current version: {self.output.highlight(self.current_version)} "
            f"({self.current_commit.sha[:7]})"
        )

    def _load_latest_info(self) -> None:
        """Determine latest available app version and config."""
        for release in self.app_repository.get_releases():
            self.latest_version = release.tag_name.lstrip("v")
            prerelease = (
                release.prerelease
                or semver.parse_version_info(self.latest_version).prerelease
            )
            if release.draft or (prerelease and self.config.channel != CHANNEL_BETA):
                continue
            self.latest_release = release
            break

        if self.latest_release:
            ref = self.app_repository.get_git_ref(
                "tags/" + self.latest_release.tag_name
            )
            self.latest_commit = self.app_repository.get_commit(ref.object.sha)

        if self.config.channel == CHANNEL_EDGE:
            last_commit = self.app_repository.get_commits()[0]
            if not self.latest_commit or last_commit.sha != self.latest_commit.sha:
                self.latest_version = last_commit.sha[:7]
                self.latest_commit = last_commit
                self.latest_is_release = False

        latest_config_file, config_file = self._fetch_latest_config_file()
        latest_config = (
            json.loads(latest_config_file.decoded_content)
            if config_file.endswith(".json")
            else yaml.safe_load(latest_config_file.decoded_content)
        )

        self._apply_config(latest_config)

        self.output.info(
            f"Latest version: {self.output.highlight(self.latest_version)} "
            f"({self.latest_commit.sha[:7]})"
        )

    def _fetch_latest_config_file(self) -> tuple[Any, str]:
        """Fetch the app configuration file belonging to the latest version."""
        config_files = list(CONFIG_FILENAMES)

        # Ensure existing filename is at the start of the list
        if self.existing_config_filename is not None:
            config_files.insert(
                0, config_files.pop(config_files.index(self.existing_config_filename))
            )

        for config_file in config_files:
            try:
                contents = self.app_repository.get_contents(
                    f"{self.config.app_target}/{config_file}", self.latest_commit.sha
                )
            except UnknownObjectException:
                continue
            return contents, config_file

        location = (
            f"{self.app_repository.full_name}/{self.config.app_target} "
            f"at {self.latest_commit.sha[:7]}"
        )
        raise AppConfigNotFoundError(location)

    def _apply_config(self, config: dict[str, Any]) -> None:
        """Copy the app details we care about out of an app configuration."""
        self.name = config["name"]
        self.description = config["description"]
        self.slug = config["slug"]
        self.url = config["url"]
        if "arch" in config:
            self.archs = config["arch"]

    def needs_update(self, *, force: bool) -> bool:
        """Determine whether or not there is app updates available."""
        return self.updating and (
            force
            or self.current_version != self.latest_version
            or self.current_commit != self.latest_commit
        )

    def ensure_app_dir(self) -> None:
        """Ensure the app target directory and its translations exist."""
        (self.target_dir / "translations").mkdir(parents=True, exist_ok=True)

    def generate_app_config(self) -> None:
        """Generate app configuration file."""
        self.output.step("Generating app configuration")

        config_file = next(
            (name for name in CONFIG_FILENAMES if (self.source_dir / name).is_file()),
            None,
        )

        if config_file is None:
            self.output.failed()
            raise AppConfigNotFoundError(str(self.source_dir))

        with (self.source_dir / config_file).open(encoding="utf8") as f:
            config = (
                json.load(f) if config_file.endswith(".json") else yaml.safe_load(f)
            )

        config["version"] = self.current_version
        config["image"] = self.config.image

        for old_config_file in CONFIG_FILENAMES:
            (self.target_dir / old_config_file).unlink(missing_ok=True)

        with (self.target_dir / config_file).open("w", encoding="utf8") as outfile:
            if config_file.endswith(".json"):
                json.dump(
                    config,
                    outfile,
                    ensure_ascii=False,
                    indent=2,
                    separators=(",", ": "),
                )
            else:
                yaml.dump(config, outfile, default_flow_style=False, sort_keys=False)

        self.output.done()

    def generate_app_changelog(self) -> None:
        """Generate app changelog."""
        self.output.step("Generating app changelog")

        changelog = ""
        if self.latest_is_release:
            changelog = self.current_release.body
        elif self.latest_release:
            compare = self.app_repository.compare(
                self.current_release.tag_name, self.current_commit.sha
            )
            changelog = f"# Changelog since {self.current_release.tag_name}\n"
            for commit in reversed(compare.commits):
                changelog += f"- {commit.commit.message} \n"
        else:
            changelog += f"- {self.current_commit.commit.message}\n"

        changelog = emoji.emojize(changelog, language="alias")

        (self.target_dir / "CHANGELOG.md").write_text(changelog, encoding="utf8")

        self.output.done()

    def update_static_files(self) -> None:
        """Update the static app files within the repository."""
        for file in STATIC_FILES:
            self.update_static(file)

    def update_static(self, file: str) -> None:
        """Download latest static file/directory from app repository."""
        self.output.step(f"Syncing app static {file}")

        local_file = self.target_dir / file
        remote_file = self.source_dir / file

        if remote_file.is_file():
            copyfile(remote_file, local_file)
            self.output.done()
        elif remote_file.is_dir():
            rmtree(local_file)
            copytree(remote_file, local_file)
            self.output.done()
        elif local_file.is_file():
            local_file.unlink()
            self.output.warning("Removed")
        else:
            self.output.skipped()

    def generate_readme(self) -> None:
        """Re-generate the app readme based on a template."""
        self.output.step("Re-generating app README.md file")

        app_file = self.source_dir / ".README.j2"
        if not app_file.is_file():
            self.output.skipped()
            return

        # Autoescaping is off on purpose: these templates render Markdown.
        jinja = Environment(  # noqa: S701
            loader=BaseLoader(),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        readme = jinja.from_string(app_file.read_text(encoding="utf8")).render(
            **self.get_template_data()
        )
        (self.target_dir / "README.md").write_text(readme, encoding="utf8")

        self.output.done()

    def get_template_data(self) -> dict[str, Any]:
        """Return a dictionary with app information."""
        data: dict[str, Any] = {}
        if not self.current_version:
            return data

        data["name"] = self.name
        data["channel"] = self.config.channel
        data["description"] = self.description
        data["url"] = self.url
        data["repo"] = self.app_repository.html_url
        data["repo_slug"] = self.app_repository.full_name
        data["archs"] = self.archs
        data["slug"] = self.slug
        data["target"] = self.config.repository_target
        data["image"] = self.config.image
        data["images"] = {}
        for arch in self.archs:
            data["images"][arch] = self.config.image.replace("{arch}", arch)

        try:
            semver.parse(self.current_version)
            data["version"] = f"v{self.current_version}"
        except ValueError:
            data["version"] = self.current_version

        data["commit"] = self.current_commit.sha

        try:
            data["date"] = self.current_release.created_at
        except AttributeError:
            data["date"] = self.current_commit.last_modified

        return data
