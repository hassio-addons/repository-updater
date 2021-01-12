#
# MIT License
#
# Copyright (c) 2018-2021 Franck Nijhof
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Add-on Module.

Represents / handles all Home Assistant add-on specific logic
"""
import json
import os
import sys
import urllib.request

import click
import crayons
import emoji
import semver
from dateutil.parser import parse
from git import Repo
from github.Commit import Commit
from github.GithubException import GithubException, UnknownObjectException
from github.GitRelease import GitRelease
from github.Repository import Repository
from jinja2 import BaseLoader, Environment

from .const import CHANNEL_BETA, CHANNEL_EDGE


class Addon:
    """Object representing an Home Assistant add-on."""

    repository_target: str
    addon_target: str
    image: str
    repository: Repo
    updating: bool
    addon_repository: Repository
    current_version: str
    current_commit: Commit
    current_release: GitRelease
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

    def __init__(
        self,
        repository: Repo,
        repository_target: str,
        image: str,
        addon_repository: Repository,
        addon_target: str,
        channel: str,
        updating: bool,
    ):
        """Initialize a new Home Assistant add-on object."""
        self.repository_target = repository_target
        self.addon_target = addon_target
        self.image = image
        self.repository = repository
        self.addon_repository = addon_repository
        self.archs = ["aarch64", "amd64", "armhf", "armv7", "i386"]
        self.latest_is_release = True
        self.updating = updating
        self.channel = channel
        self.current_version = None
        self.latest_release = None
        self.latest_commit = None

        click.echo(
            "Loading add-on information from: %s" % self.addon_repository.html_url
        )

        self.__load_current_info()
        if self.updating:
            self.__load_latest_info(channel)
            if self.needs_update(False):
                click.echo(
                    crayons.yellow("This add-on has an update waiting to be published!")
                )
            else:
                click.echo(crayons.green("This add-on is up to date."))

    def update(self):
        """Update this add-on inside the given add-on repository."""
        if not self.updating:
            click.echo(
                crayons.red("Cannot update add-on that was marked not being updated")
            )
            sys.exit(1)

        self.current_version = self.latest_version
        self.current_release = self.latest_release
        self.current_commit = self.latest_commit

        self.ensure_addon_dir()
        self.generate_addon_config()
        self.update_static_files()
        self.generate_readme()
        self.generate_addon_changelog()

    def __load_current_info(self):
        """Load current add-on version information and current config."""
        current_config_file = os.path.join(
            self.repository.working_dir, self.repository_target, "config.json"
        )

        if not os.path.isfile(current_config_file):
            click.echo("Current version: %s" % crayons.yellow("Not available"))
            return False

        current_config = json.load(open(current_config_file))
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
                ref = self.addon_repository.get_git_ref("tags/" + self.current_version)
            except UnknownObjectException:
                ref = self.addon_repository.get_git_ref("tags/v" + self.current_version)
            self.current_commit = self.addon_repository.get_commit(ref.object.sha)
        else:
            try:
                self.current_commit = self.addon_repository.get_commit(
                    f"v{self.current_version}"
                )
            except GithubException:
                self.current_commit = self.addon_repository.get_commit(
                    self.current_version
                )

        click.echo(
            "Current version: %s (%s)"
            % (crayons.magenta(self.current_version), self.current_commit.sha[:7])
        )

    def __load_latest_info(self, channel: str):
        """Determine latest available add-on version and config."""
        for release in self.addon_repository.get_releases():
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
            ref = self.addon_repository.get_git_ref(
                "tags/" + self.latest_release.tag_name
            )
            self.latest_commit = self.addon_repository.get_commit(ref.object.sha)

        if channel == CHANNEL_EDGE:
            last_commit = self.addon_repository.get_commits()[0]
            if not self.latest_commit or last_commit.sha != self.latest_commit.sha:
                self.latest_version = last_commit.sha[:7]
                self.latest_commit = last_commit
                self.latest_is_release = False

        try:
            latest_config_file = self.addon_repository.get_contents(
                os.path.join(self.addon_target, "config.json"), self.latest_commit.sha
            )
            latest_config = json.loads(latest_config_file.decoded_content)
            self.name = latest_config["name"]
            self.description = latest_config["description"]
            self.slug = latest_config["slug"]
            self.url = latest_config["url"]
            if "arch" in latest_config:
                self.archs = latest_config["arch"]

        except UnknownObjectException:
            click.echo(
                crayons.red(
                    "An error occurred while loading the remote add-on "
                    "configuration file"
                )
            )
            sys.exit(1)

        click.echo(
            "Latest version: %s (%s)"
            % (crayons.magenta(self.latest_version), self.latest_commit.sha[:7])
        )

    def needs_update(self, force: bool):
        """Determine whether or not there is add-on updates available."""
        return self.updating and (
            force
            or self.current_version != self.latest_version
            or self.current_commit != self.latest_commit
        )

    def ensure_addon_dir(self):
        """Ensure the add-on target directory exists."""
        addon_path = os.path.join(self.repository.working_dir, self.repository_target)

        if not os.path.exists(addon_path):
            os.mkdir(addon_path)

    def generate_addon_config(self):
        """Generate add-on configuration file."""
        click.echo("Generating add-on configuration...", nl=False)
        try:
            config = self.addon_repository.get_contents(
                os.path.join(self.addon_target, "config.json"), self.current_commit.sha
            )
        except UnknownObjectException:
            click.echo(crayons.red("Failed!"))
            sys.exit(1)

        config = json.loads(config.decoded_content)
        config["version"] = self.current_version
        config["image"] = self.image

        with open(
            os.path.join(
                self.repository.working_dir, self.repository_target, "config.json"
            ),
            "w",
        ) as outfile:
            json.dump(
                config, outfile, ensure_ascii=False, indent=2, separators=(",", ": ")
            )

        click.echo(crayons.green("Done"))

    def generate_addon_changelog(self):
        """Generate add-on changelog."""
        click.echo("Generating add-on changelog...", nl=False)
        changelog = ""
        if self.latest_is_release:
            changelog = self.current_release.body
        elif self.latest_release:
            compare = self.addon_repository.compare(
                self.current_release.tag_name, self.current_commit.sha
            )
            changelog = "# Changelog since %s\n" % self.current_release.tag_name
            for commit in reversed(compare.commits):
                changelog += "- %s \n" % (commit.commit.message)
        else:
            changelog += "- %s\n" % (self.current_commit.commit.message)

        changelog = emoji.emojize(changelog, use_aliases=True)

        with open(
            os.path.join(
                self.repository.working_dir, self.repository_target, "CHANGELOG.md"
            ),
            "w",
        ) as outfile:
            outfile.write(changelog)

        click.echo(crayons.green("Done"))

    def update_static_files(self):
        """Update the static add-on files within the repository."""
        self.update_static_file("logo.png")
        self.update_static_file("icon.png")
        self.update_static_file("README.md")
        self.update_static_file("DOCS.md")

    def update_static_file(self, file):
        """Download latest static file from add-on repository."""
        click.echo(f"Syncing add-on static file {file}...", nl=False)
        addon_file = os.path.join(self.addon_target, file)
        local_file = os.path.join(
            self.repository.working_dir, self.repository_target, file
        )
        remote_file = False
        try:
            remote_file = self.addon_repository.get_contents(
                addon_file, self.current_commit.sha
            )
        except UnknownObjectException:
            pass

        if remote_file:
            urllib.request.urlretrieve(remote_file.download_url, local_file)
            click.echo(crayons.green("Done"))
        elif os.path.isfile(local_file):
            os.remove(os.path.join(local_file))
            click.echo(crayons.yellow("Removed"))
        else:
            click.echo(crayons.blue("Skipping"))

    def generate_readme(self):
        """Re-generate the add-on readme based on a template."""
        click.echo("Re-generating add-on README.md file...", nl=False)

        addon_file = os.path.join(self.addon_target, ".README.j2")
        local_file = os.path.join(
            self.repository.working_dir, self.repository_target, "README.md"
        )

        try:
            remote_file = self.addon_repository.get_contents(
                addon_file, self.current_commit.sha
            )
        except UnknownObjectException:
            click.echo(crayons.blue("Skipping"))
            return

        data = self.get_template_data()

        jinja = Environment(
            loader=BaseLoader(),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        with open(local_file, "w") as outfile:
            outfile.write(
                jinja.from_string(remote_file.decoded_content.decode("utf8")).render(
                    **data
                )
            )

        click.echo(crayons.green("Done"))

    def get_template_data(self):
        """Return a dictionary with add-on information."""
        data = {}
        if not self.current_version:
            return data

        data["name"] = self.name
        data["channel"] = self.channel
        data["description"] = self.description
        data["url"] = self.url
        data["repo"] = self.addon_repository.html_url
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
