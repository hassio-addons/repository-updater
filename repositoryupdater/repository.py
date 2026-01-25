"""
Repository module.

Contains the apps repository representation / configuration
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

from .app import App
from .const import CHANNELS
from .github import GitHub


class Repository:
    """Represents an Home Assistant apps repository."""

    apps: List[App]
    github: GitHub
    github_repository: GitHubRepository
    git_repo: Repo
    force: bool
    channel: str

    def __init__(self, github: GitHub, repository: str, app: str, force: bool):
        """Initialize new app Repository object."""
        self.github = github
        self.force = force
        self.apps = []

        click.echo(
            'Locating app repository "%s"...' % crayons.yellow(repository), nl=False
        )
        self.github_repository = github.get_repo(repository)
        click.echo(crayons.green("Found!"))

        self.clone_repository()
        self.load_repository(app)

    def update(self):
        """Update this repository using configuration and data gathered."""
        self.generate_readme()
        needs_push = self.commit_changes(":books: Updated README")

        for app in self.apps:
            if app.needs_update(self.force):
                click.echo(crayons.green("-" * 50, bold=True))
                click.echo(crayons.green(f"Updating app {app.repository_target}"))
                needs_push = self.update_app(app) or needs_push

        if needs_push:
            click.echo(crayons.green("-" * 50, bold=True))
            click.echo("Pushing updates onto Git apps repository...", nl=False)
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

    def update_app(self, app):
        """Update repository for a specific app."""
        app.update()
        self.generate_readme()

        if app.latest_is_release:
            message = ":tada: Release of app %s %s" % (
                app.name,
                app.current_version,
            )
        else:
            message = ":arrow_up: Updating app %s to %s" % (
                app.name,
                app.current_version,
            )
        if self.force:
            message += " (forced update)"

        return self.commit_changes(message)

    def load_repository(self, app: str):
        """Load repository configuration from remote repository and apps."""
        click.echo("Locating repository app list...", nl=False)
        config = None
        for config_file in (".apps.yml", ".addons.yml", ".hassio-addons.yml"):
            try:
                config = self.github_repository.get_contents(config_file)
                break
            except UnknownObjectException:
                continue

        if config is None:
            click.echo(crayons.red("Failed!"))
            click.echo(
                crayons.red(
                    "Repository does not contain an .apps.yml, "
                    ".addons.yml, or .hassio-addons.yml file."
                )
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

        if app:
            click.echo(crayons.yellow('Only updating app "%s" this run!' % app))

        click.echo("Start loading repository apps:")
        apps_config = config.get("apps", config.get("addons", {}))
        for target, app_config in apps_config.items():
            click.echo(crayons.cyan("-" * 50, bold=True))
            click.echo(crayons.cyan(f"Loading app {target}"))
            self.apps.append(
                App(
                    self.github,
                    self.git_repo,
                    target,
                    app_config["image"],
                    self.github.get_repo(app_config["repository"]),
                    app_config["target"],
                    self.channel,
                    (
                        not app
                        or app_config["repository"] == app
                        or target == app
                    ),
                )
            )
        click.echo(crayons.cyan("-" * 50, bold=True))
        click.echo("Done loading all repository apps")

    def clone_repository(self):
        """Clone the app repository to a local working directory."""
        click.echo("Cloning app repository...", nl=False)
        self.git_repo = self.github.clone(
            self.github_repository, tempfile.mkdtemp(prefix="repoupdater")
        )
        click.echo(crayons.green("Cloned!"))

    def generate_readme(self):
        """Re-generate the repository readme based on a template."""
        click.echo("Re-generating app repository README.md file...", nl=False)

        if not os.path.exists(os.path.join(self.git_repo.working_dir, ".README.j2")):
            click.echo(crayons.blue("skipping"))
            return

        app_data = []
        for app in self.apps:
            data = app.get_template_data()
            if data:
                app_data.append(app.get_template_data())

        app_data = sorted(app_data, key=lambda x: x["name"])

        jinja = Environment(
            loader=FileSystemLoader(self.git_repo.working_dir),
            trim_blocks=True,
            extensions=["jinja2.ext.loopcontrols"],
        )

        with open(
            os.path.join(self.git_repo.working_dir, "README.md"), "w", encoding="utf8"
        ) as outfile:
            outfile.write(
                jinja.get_template(".README.j2").render(
                    apps=app_data,
                    addons=app_data,  # Backward compatibility
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
