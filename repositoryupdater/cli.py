"""
CLI Module.

Handles CLI for the Repository Updater
"""

from __future__ import annotations

import sys
from os import environ
from sys import argv

import click
import crayons

from . import APP_FULL_NAME, APP_VERSION
from .github import GitHub
from .repository import Repository


@click.command()
@click.option(
    "--token",
    hide_input=True,
    prompt="GitHub access token",
    help="GitHub access token",
    metavar="<TOKEN>",
)
@click.option(
    "--repository",
    prompt="Home Assistant Apps repository to update",
    help="The Home Assistant Apps repository to update",
    metavar="<orgname/reponame>",
)
@click.option(
    "--app",
    "--addon",
    "app",
    help="Update a single/specific app",
    metavar="<TARGET>",
)
@click.option("--force", is_flag=True, help="Force an update of the app repository")
@click.version_option(APP_VERSION, prog_name=APP_FULL_NAME)
def repository_updater(
    token: str,
    repository: str,
    app: str | None,
    force: bool,
) -> None:
    """Home Assistant Community Apps Repository Updater."""
    click.echo(crayons.blue(APP_FULL_NAME, bold=True))
    click.echo(crayons.blue("-" * 51, bold=True))

    github = GitHub(token)
    user = crayons.yellow(github.get_user().name, bold=True)
    click.echo(f"Authenticated with GitHub as {user}")

    apps_repository = Repository(github, repository, app, force)
    apps_repository.update()
    apps_repository.cleanup()


def git_askpass() -> None:
    """
    Git credentials helper.

    Short & sweet script for use with git clone and fetch credentials.
    Requires GIT_USERNAME and GIT_PASSWORD environment variables,
    intended to be called by Git via GIT_ASKPASS.
    """
    if argv[1] == "Username for 'https://github.com': ":
        print(environ["GIT_USERNAME"])  # noqa: T201
        sys.exit()

    if argv[1] == f"Password for 'https://{environ['GIT_USERNAME']}@github.com': ":
        print(environ["GIT_PASSWORD"])  # noqa: T201
        sys.exit()

    sys.exit(1)
