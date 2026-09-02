"""
Repository module.

Contains the apps repository representation / configuration
and handles the automated maintenance / updating of it.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from github.GithubException import UnknownObjectException
from jinja2 import Environment, FileSystemLoader

from .app import App, AppConfig
from .const import APP_LIST_FILENAMES, CHANNELS
from .exceptions import InvalidChannelError, RepositoryAppListNotFoundError

if TYPE_CHECKING:
    from git import Repo
    from github.Repository import Repository as GitHubRepository

    from .github import GitHub
    from .output import Output


class Repository:
    """Represents an Home Assistant apps repository."""

    apps: list[App]
    github_repository: GitHubRepository | None
    git_repo: Repo | None
    clone_dir: Path | None
    channel: str | None

    def __init__(
        self,
        github: GitHub,
        repository: str,
        app: str | None,
        *,
        force: bool,
        output: Output,
    ) -> None:
        """Initialize new app Repository object."""
        self.github = github
        self.repository = repository
        self.app_filter = app
        self.force = force
        self.output = output

        self.apps = []
        self.github_repository = None
        self.git_repo = None
        self.clone_dir = None
        self.channel = None

    def load(self) -> None:
        """Locate the apps repository, clone it and load the apps it holds."""
        self.output.step(
            f'Locating app repository "{self.output.emphasis(self.repository)}"'
        )
        self.github_repository = self.github.get_repo(self.repository)
        self.output.done("Found!")

        self.clone_repository()
        self.load_apps()

    def update(self) -> None:
        """Update this repository using configuration and data gathered."""
        self.generate_readme()
        needs_push = self.commit_changes(":books: Updated README")

        for app in self.apps:
            if app.needs_update(force=self.force):
                self.output.divider()
                self.output.success(f"Updating app {app.config.repository_target}")
                needs_push = self.update_app(app) or needs_push

        if needs_push:
            self.output.divider()
            self.output.step("Pushing updates onto Git apps repository")
            self.git_repo.git.push()
            self.output.done()

    def commit_changes(self, message: str) -> bool:
        """Commit current Repository changes."""
        self.output.step("Committing changes")

        if not self.git_repo.is_dirty(untracked_files=True):
            self.output.warning("Skipped, no changes.")
            return False

        self.git_repo.git.add(".")
        self.git_repo.git.commit("--no-gpg-sign", "-m", message)
        self.output.done(f"Done: {message}")
        return True

    def update_app(self, app: App) -> bool:
        """Update repository for a specific app."""
        app.update()
        self.generate_readme()

        if app.latest_is_release:
            message = f":tada: Release of app {app.name} {app.current_version}"
        else:
            message = f":arrow_up: Updating app {app.name} to {app.current_version}"
        if self.force:
            message += " (forced update)"

        return self.commit_changes(message)

    def load_apps(self) -> None:
        """Load repository configuration from remote repository and apps."""
        config = self._fetch_app_list()

        if config["channel"] not in CHANNELS:
            raise InvalidChannelError(config["channel"])

        self.channel = config["channel"]
        self.output.info(f"Repository channel: {self.output.highlight(self.channel)}")

        if self.app_filter:
            self.output.warning(f'Only updating app "{self.app_filter}" this run!')

        self.output.info("Start loading repository apps:")
        apps_config = config.get("apps", config.get("addons", {}))
        for target, app_config in apps_config.items():
            self.output.section(f"Loading app {target}")
            app = App(
                self.github,
                Path(self.git_repo.working_dir),
                AppConfig.from_app_list(target, app_config, self.channel),
                updating=self._is_selected(target, app_config["repository"]),
                output=self.output,
            )
            app.load()
            self.apps.append(app)

        self.output.section("Done loading all repository apps")

    def _fetch_app_list(self) -> dict:
        """Fetch and parse the app list declared by the apps repository."""
        self.output.step("Locating repository app list")

        for config_file in APP_LIST_FILENAMES:
            try:
                contents = self.github_repository.get_contents(config_file)
            except UnknownObjectException:
                continue
            app_list = yaml.safe_load(contents.decoded_content)
            self.output.done("Loaded!")
            return app_list

        self.output.failed()
        raise RepositoryAppListNotFoundError(APP_LIST_FILENAMES)

    def _is_selected(self, target: str, repository: str) -> bool:
        """Return whether an app is in scope for this run."""
        if not self.app_filter:
            return True
        return self.app_filter in (target, repository)

    def clone_repository(self) -> None:
        """Clone the app repository to a local working directory."""
        self.output.step("Cloning app repository")
        self.clone_dir = Path(tempfile.mkdtemp(prefix="repoupdater"))
        self.git_repo = self.github.clone(self.github_repository, str(self.clone_dir))
        self.output.done("Cloned!")

    def generate_readme(self) -> None:
        """Re-generate the repository readme based on a template."""
        self.output.step("Re-generating app repository README.md file")

        working_dir = Path(self.git_repo.working_dir)
        if not (working_dir / ".README.j2").is_file():
            self.output.skipped()
            return

        app_data = [data for app in self.apps if (data := app.get_template_data())]
        app_data = sorted(app_data, key=lambda x: x["name"])

        # Autoescaping is off on purpose: these templates render Markdown.
        jinja = Environment(  # noqa: S701
            loader=FileSystemLoader(self.git_repo.working_dir),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        readme = jinja.get_template(".README.j2").render(
            apps=app_data,
            addons=app_data,  # Backward compatibility
            channel=self.channel,
            description=self.github_repository.description,
            homepage=self.github_repository.homepage,
            issues=self.github_repository.issues_url,
            name=self.github_repository.full_name,
            repo=self.github_repository.html_url,
        )
        (working_dir / "README.md").write_text(readme, encoding="utf8")

        self.output.done()

    def cleanup(self) -> None:
        """Remove every temporary clone this run created."""
        self.output.step("Cleanup")

        for app in self.apps:
            app.cleanup()

        # Owned by us because we created it, so it goes even when the clone
        # itself never finished and self.git_repo was left unset.
        if self.clone_dir is not None:
            shutil.rmtree(self.clone_dir, ignore_errors=True)
            self.clone_dir = None

        self.output.done()
