"""
CLI Module.

Handles CLI for the Repository Updater
"""

from __future__ import annotations

import sys
from os import environ
from sys import argv

import click

from . import APP_FULL_NAME, APP_VERSION
from .exceptions import RepositoryUpdaterError
from .github import GitHub
from .output import Output
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
    *,
    token: str,
    repository: str,
    app: str | None,
    force: bool,
) -> None:
    """Home Assistant Community Apps Repository Updater."""
    output = Output()
    output.title(APP_FULL_NAME)

    try:
        github = GitHub(token)
        output.info(
            f"Authenticated with GitHub as {output.emphasis(github.get_user().name)}"
        )

        apps_repository = Repository(
            github, repository, app, force=force, output=output
        )
        try:
            apps_repository.load()
            apps_repository.update()
        finally:
            apps_repository.cleanup()
    except RepositoryUpdaterError as err:
        raise click.ClickException(str(err)) from err


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
