"""
Apps Module.

Represents / handles all Home Assistant app specific logic
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from shutil import copyfile, copytree, rmtree

import click
import crayons
import emoji
import semver
import yaml
from git import Repo
from github.Commit import Commit
from github.GithubException import GithubException, UnknownObjectException
from github.GitRelease import GitRelease
from github.Repository import Repository
from jinja2 import BaseLoader, Environment

from repositoryupdater.github import GitHub

from .const import CHANNEL_BETA, CHANNEL_EDGE


class App:
    """Object representing an Home Assistant app."""

    repository_target: str
    app_target: str
    image: str
    repository: Repo
    updating: bool
    app_repository: Repository
    current_version: str
    current_commit: Commit
    current_release: GitRelease
    existing_config_filename: str | None = None
    latest_version: str
    latest_release: GitRelease
    latest_is_release: bool
    latest_commit: Commit
    archs: list
    name: str
    description: str
    slug: str
    url: str
    channel: str
    github: GitHub
    git_repo: Repo

    def __init__(
        self,
        github: GitHub,
        repository: Repo,
        repository_target: str,
        image: str,
        app_repository: Repository,
        app_target: str,
        channel: str,
        updating: bool,
    ):
        """Initialize a new Home Assistant app object."""
        self.github = github
        self.repository_target = repository_target
        self.app_target = app_target
        self.image = image
        self.repository = repository
        self.app_repository = app_repository
        self.archs = ["aarch64", "amd64", "armhf", "armv7", "i386"]
        self.latest_is_release = True
        self.updating = updating
        self.channel = channel
        self.current_version = None
        self.latest_release = None
        self.latest_commit = None

        click.echo(
            "Loading app information from: %s" % self.app_repository.html_url
        )

        self.__load_current_info()
        if self.updating:
            self.__load_latest_info(channel)
            if self.needs_update(False):
                click.echo(
                    crayons.yellow("This app has an update waiting to be published!")
                )
            else:
                click.echo(crayons.green("This app is up to date."))

    def clone_repository(self):
        """Clone the app source to a local working directory."""
        click.echo("Cloning app git repository...", nl=False)
        self.git_repo = self.github.clone(
            self.app_repository, tempfile.mkdtemp(prefix=self.app_target)
        )
        self.git_repo.git.checkout(self.current_commit.sha)
        click.echo(crayons.green("Cloned!"))

    def update(self):
        """Update this app inside the given app repository."""
        if not self.updating:
            click.echo(
                crayons.red("Cannot update app that was marked not being updated")
            )
            sys.exit(1)

        self.current_version = self.latest_version
        self.current_release = self.latest_release
        self.current_commit = self.latest_commit

        self.clone_repository()
        self.ensure_app_dir()
        self.generate_app_config()
        self.update_static_files()
        self.generate_readme()
        self.generate_app_changelog()

    def __load_current_info(self):
        """Load current app version information and current config."""
        config_files = ("config.json", "config.yaml", "config.yml")
        for config_file in config_files:
            if os.path.exists(
                os.path.join(
                    self.repository.working_dir, self.repository_target, config_file
                )
            ):
                self.existing_config_filename = config_file
                break

        if self.existing_config_filename is None:
            click.echo("Current version: %s" % crayons.yellow("Not available"))
            return False

        with open(
            os.path.join(
                self.repository.working_dir,
                self.repository_target,
                self.existing_config_filename,
            ),
            "r",
            encoding="utf8",
        ) as f:
            current_config = (
                json.load(f)
                if self.existing_config_filename.endswith(".json")
                else yaml.safe_load(f)
            )

        self.current_version = current_config["version"]
        self.name = current_config["name"]
        self.description = current_config["description"]
        self.slug = current_config["slug"]
        self.url = current_config["url"]
        if "arch" in current_config:
            self.archs = current_config["arch"]

        current_parsed_version = False
        try:
            current_parsed_version = semver.parse(self.current_version)
        except ValueError:
            pass

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

        click.echo(
            "Current version: %s (%s)"
            % (crayons.magenta(self.current_version), self.current_commit.sha[:7])
        )

    def __load_latest_info(self, channel: str):
        """Determine latest available app version and config."""
        for release in self.app_repository.get_releases():
            self.latest_version = release.tag_name.lstrip("v")
            prerelease = (
                release.prerelease
                or semver.parse_version_info(self.latest_version).prerelease
            )
            if release.draft or (prerelease and channel != CHANNEL_BETA):
                continue
            self.latest_release = release
            break

        if self.latest_release:
            ref = self.app_repository.get_git_ref(
                "tags/" + self.latest_release.tag_name
            )
            self.latest_commit = self.app_repository.get_commit(ref.object.sha)

        if channel == CHANNEL_EDGE:
            last_commit = self.app_repository.get_commits()[0]
            if not self.latest_commit or last_commit.sha != self.latest_commit.sha:
                self.latest_version = last_commit.sha[:7]
                self.latest_commit = last_commit
                self.latest_is_release = False

        config_files = ["config.json", "config.yaml", "config.yml"]
        # Ensure existing filename is at the start of the list
        if self.existing_config_filename is not None:
            config_files.insert(
                0, config_files.pop(config_files.index(self.existing_config_filename))
            )

        latest_config_file = None
        config_file = None
        for config_file in config_files:
            try:
                latest_config_file = self.app_repository.get_contents(
                    os.path.join(self.app_target, config_file), self.latest_commit.sha
                )
                break
            except UnknownObjectException:
                pass

        if config_file is None or latest_config_file is None:
            click.echo(
                crayons.red(
                    "An error occurred while loading the remote app "
                    "configuration file"
                )
            )
            sys.exit(1)

        latest_config = (
            json.loads(latest_config_file.decoded_content)
            if config_file.endswith(".json")
            else yaml.safe_load(latest_config_file.decoded_content)
        )

        self.name = latest_config["name"]
        self.description = latest_config["description"]
        self.slug = latest_config["slug"]
        self.url = latest_config["url"]
        if "arch" in latest_config:
            self.archs = latest_config["arch"]

        click.echo(
            "Latest version: %s (%s)"
            % (crayons.magenta(self.latest_version), self.latest_commit.sha[:7])
        )

    def needs_update(self, force: bool):
        """Determine whether or not there is app updates available."""
        return self.updating and (
            force
            or self.current_version != self.latest_version
            or self.current_commit != self.latest_commit
        )

    def ensure_app_dir(self):
        """Ensure the app target directory exists."""
        app_path = os.path.join(self.repository.working_dir, self.repository_target)
        app_translations_path = os.path.join(app_path, "translations")

        if not os.path.exists(app_path):
            os.mkdir(app_path)

        if not os.path.exists(app_translations_path):
            os.mkdir(app_translations_path)

    def generate_app_config(self):
        """Generate app configuration file."""
        click.echo("Generating app configuration...", nl=False)

        config_files = ("config.json", "config.yaml", "config.yml")
        config_file = None
        for config_file in config_files:
            if os.path.exists(
                os.path.join(self.git_repo.working_dir, self.app_target, config_file)
            ):
                break
            config_file = None

        if config_file is None:
            click.echo(crayons.red("Failed!"))
            sys.exit(1)

        with open(
            os.path.join(self.git_repo.working_dir, self.app_target, config_file),
            encoding="utf8",
        ) as f:
            config = (
                json.load(f) if config_file.endswith(".json") else yaml.safe_load(f)
            )

        config["version"] = self.current_version
        config["image"] = self.image

        for old_config_file in config_files:
            try:
                os.unlink(
                    os.path.join(
                        self.repository.working_dir,
                        self.repository_target,
                        old_config_file,
                    )
                )
            except:
                pass

        with open(
            os.path.join(
                self.repository.working_dir, self.repository_target, config_file
            ),
            "w",
            encoding="utf8",
        ) as outfile:
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

        click.echo(crayons.green("Done"))

    def generate_app_changelog(self):
        """Generate app changelog."""
        click.echo("Generating app changelog...", nl=False)
        changelog = ""
        if self.latest_is_release:
            changelog = self.current_release.body
        elif self.latest_release:
            compare = self.app_repository.compare(
                self.current_release.tag_name, self.current_commit.sha
            )
            changelog = "# Changelog since %s\n" % self.current_release.tag_name
            for commit in reversed(compare.commits):
                changelog += "- %s \n" % (commit.commit.message)
        else:
            changelog += "- %s\n" % (self.current_commit.commit.message)

        changelog = emoji.emojize(changelog, language="alias")

        with open(
            os.path.join(
                self.repository.working_dir, self.repository_target, "CHANGELOG.md"
            ),
            "w",
            encoding="utf8",
        ) as outfile:
            outfile.write(changelog)

        click.echo(crayons.green("Done"))

    def update_static_files(self):
        """Update the static app files within the repository."""
        self.update_static("logo.png")
        self.update_static("icon.png")
        self.update_static("README.md")
        self.update_static("DOCS.md")
        self.update_static("apparmor.txt")
        self.update_static("translations")

    def update_static(self, file):
        """Download latest static file/directory from app repository."""
        click.echo(f"Syncing app static {file}...", nl=False)
        local_file = os.path.join(
            self.repository.working_dir, self.repository_target, file
        )
        remote_file = os.path.join(self.git_repo.working_dir, self.app_target, file)

        if os.path.exists(remote_file) and os.path.isfile(remote_file):
            copyfile(remote_file, local_file)
            click.echo(crayons.green("Done"))
        elif os.path.exists(remote_file) and os.path.isdir(remote_file):
            rmtree(local_file)
            copytree(remote_file, local_file)
            click.echo(crayons.green("Done"))
        elif os.path.isfile(local_file):
            os.remove(local_file)
            click.echo(crayons.yellow("Removed"))
        else:
            click.echo(crayons.blue("Skipping"))

    def generate_readme(self):
        """Re-generate the app readme based on a template."""
        click.echo("Re-generating app README.md file...", nl=False)

        app_file = os.path.join(
            self.git_repo.working_dir, self.app_target, ".README.j2"
        )
        if not os.path.exists(app_file):
            click.echo(crayons.blue("Skipping"))
            return

        local_file = os.path.join(
            self.repository.working_dir, self.repository_target, "README.md"
        )

        data = self.get_template_data()

        jinja = Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        with open(local_file, "w", encoding="utf8") as outfile:
            outfile.write(
                jinja.from_string(open(app_file, encoding="utf8").read()).render(
                    **data
                )
            )

        click.echo(crayons.green("Done"))

    def get_template_data(self):
        """Return a dictionary with app information."""
        data = {}
        if not self.current_version:
            return data

        data["name"] = self.name
        data["channel"] = self.channel
        data["description"] = self.description
        data["url"] = self.url
        data["repo"] = self.app_repository.html_url
        data["repo_slug"] = self.app_repository.full_name
        data["archs"] = self.archs
        data["slug"] = self.slug
        data["target"] = self.repository_target
        data["image"] = self.image
        data["images"] = {}
        for arch in self.archs:
            data["images"][arch] = self.image.replace("{arch}", arch)

        try:
            semver.parse(self.current_version)
            data["version"] = "v%s" % self.current_version
        except ValueError:
            data["version"] = self.current_version

        data["commit"] = self.current_commit.sha

        try:
            data["date"] = self.current_release.created_at
        except AttributeError:
            data["date"] = self.current_commit.last_modified

        return data
