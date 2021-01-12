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
Repository module.

Contains the add-ons repository representation / configuration
and handles the automated maintenance / updating of it.
"""
import os
import shutil
import sys
import tempfile
from typing import List

import click
import crayons
import yaml
from git import Repo
from github.GithubException import UnknownObjectException
from github.Repository import Repository as GitHubRepository
from jinja2 import Environment, FileSystemLoader

from .addon import Addon
from .const import CHANNELS
from .github import GitHub


class Repository:
    """Represents an Home Assistant add-ons repository."""

    addons: List[Addon]
    github: GitHub
    github_repository: GitHubRepository
    git_repo: Repo
    force: bool
    channel: str

    def __init__(self, github: GitHub, repository: str, addon: str, force: bool):
        """Initialize new add-on Repository object."""
        self.github = github
        self.force = force
        self.addons = []

        click.echo(
            'Locating add-on repository "%s"...' % crayons.yellow(repository), nl=False
        )
        self.github_repository = github.get_repo(repository)
        click.echo(crayons.green("Found!"))

        self.clone_repository()
        self.load_repository(addon)

    def update(self):
        """Update this repository using configuration and data gathered."""
        self.generate_readme()
        needs_push = self.commit_changes(":books: Updated README")

        for addon in self.addons:
            if addon.needs_update(self.force):
                click.echo(crayons.green("-" * 50, bold=True))
                click.echo(crayons.green(f"Updating add-on {addon.repository_target}"))
                needs_push = self.update_addon(addon) or needs_push

        if needs_push:
            click.echo(crayons.green("-" * 50, bold=True))
            click.echo("Pushing updates onto Git add-ons repository...", nl=False)
            self.git_repo.git.push()
            click.echo(crayons.green("Done"))

    def commit_changes(self, message):
        """Commit current Repository changes."""
        click.echo("Committing changes...", nl=False)

        if not self.git_repo.is_dirty(untracked_files=True):
            click.echo(crayons.yellow("Skipped, no changes."))
            return False

        self.git_repo.git.add(".")
        self.git_repo.git.commit("--no-gpg-sign", "-m", message)
        click.echo(crayons.green("Done: ") + crayons.cyan(message))
        return True

    def update_addon(self, addon):
        """Update repository for a specific add-on."""
        addon.update()
        self.generate_readme()

        if addon.latest_is_release:
            message = ":tada: Release of add-on %s %s" % (
                addon.name,
                addon.current_version,
            )
        else:
            message = ":arrow_up: Updating add-on %s to %s" % (
                addon.name,
                addon.current_version,
            )
        if self.force:
            message += " (forced update)"

        return self.commit_changes(message)

    def load_repository(self, addon: str):
        """Load repository configuration from remote repository and add-ons."""
        click.echo("Locating repository add-on list...", nl=False)
        try:
            config = self.github_repository.get_contents(".addons.yml")
        except UnknownObjectException:
            print(
                "Seems like the repository does not contain an "
                ".addons.yml file, falling back to legacy file."
            )
            try:
                config = self.github_repository.get_contents(".hassio-addons.yml")
            except UnknownObjectException:
                print(
                    "Seems like the repository does not contain an "
                    ".hassio-addons.yml file either."
                )
                sys.exit(1)

        config = yaml.safe_load(config.decoded_content)
        click.echo(crayons.green("Loaded!"))

        if config["channel"] not in CHANNELS:
            click.echo(
                crayons.red(
                    'Channel "%s" is not a valid channel identifier' % config["channel"]
                )
            )
            sys.exit(1)

        self.channel = config["channel"]
        click.echo("Repository channel: %s" % crayons.magenta(self.channel))

        if addon:
            click.echo(crayons.yellow('Only updating addon "%s" this run!' % addon))

        click.echo("Start loading repository add-ons:")
        for target, addon_config in config["addons"].items():
            click.echo(crayons.cyan("-" * 50, bold=True))
            click.echo(crayons.cyan(f"Loading add-on {target}"))
            self.addons.append(
                Addon(
                    self.git_repo,
                    target,
                    addon_config["image"],
                    self.github.get_repo(addon_config["repository"]),
                    addon_config["target"],
                    self.channel,
                    (
                        not addon
                        or addon_config["repository"] == addon
                        or target == addon
                    ),
                )
            )
        click.echo(crayons.cyan("-" * 50, bold=True))
        click.echo("Done loading all repository add-ons")

    def clone_repository(self):
        """Clone the add-on repository to a local working directory."""
        click.echo("Cloning add-on repository...", nl=False)
        self.git_repo = self.github.clone(
            self.github_repository, tempfile.mkdtemp(prefix="repoupdater")
        )
        click.echo(crayons.green("Cloned!"))

    def generate_readme(self):
        """Re-generate the repository readme based on a template."""
        click.echo("Re-generating add-on repository README.md file...", nl=False)

        if not os.path.exists(os.path.join(self.git_repo.working_dir, ".README.j2")):
            click.echo(crayons.blue("skipping"))
            return

        addon_data = []
        for addon in self.addons:
            data = addon.get_template_data()
            if data:
                addon_data.append(addon.get_template_data())

        addon_data = sorted(addon_data, key=lambda x: x["name"])

        jinja = Environment(
            loader=FileSystemLoader(self.git_repo.working_dir),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        with open(os.path.join(self.git_repo.working_dir, "README.md"), "w") as outfile:
            outfile.write(
                jinja.get_template(".README.j2").render(
                    addons=addon_data,
                    channel=self.channel,
                    description=self.github_repository.description,
                    homepage=self.github_repository.homepage,
                    issues=self.github_repository.issues_url,
                    name=self.github_repository.full_name,
                    repo=self.github_repository.html_url,
                )
            )

        click.echo(crayons.green("Done"))

    def cleanup(self):
        """Cleanup after you leave."""
        click.echo("Cleanup...", nl=False)
        shutil.rmtree(self.git_repo.working_dir, True)
        click.echo(crayons.green("Done"))
