"""
CLI Module.

Handles CLI for the Repository Updater
"""
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
    prompt="Home Assistant Addons repository to update",
    help="The Home Assistant Addons repository to update",
    metavar="<orgname/reponame>",
)
@click.option("--addon", help="Update a single/specific add-on", metavar="<TARGET>")
@click.option("--force", is_flag=True, help="Force an update of the add-on repository")
@click.version_option(APP_VERSION, prog_name=APP_FULL_NAME)
def repository_updater(token, repository, addon, force):
    """Community Home Assistant Add-ons Repository Updater."""
    click.echo(crayons.blue(APP_FULL_NAME, bold=True))
    click.echo(crayons.blue("-" * 51, bold=True))
    github = GitHub(token)
    click.echo(
        "Authenticated with GitHub as %s"
        % crayons.yellow(github.get_user().name, bold=True)
    )
    repository = Repository(github, repository, addon, force)
    repository.update()
    repository.cleanup()


def git_askpass():
    """
    Git credentials helper.

    Short & sweet script for use with git clone and fetch credentials.
    Requires GIT_USERNAME and GIT_PASSWORD environment variables,
    intended to be called by Git via GIT_ASKPASS.
    """
    if argv[1] == "Username for 'https://github.com': ":
        print(environ["GIT_USERNAME"])
        sys.exit()

    if argv[1] == "Password for 'https://" "%(GIT_USERNAME)s@github.com': " % environ:
        print(environ["GIT_PASSWORD"])
        sys.exit()

    sys.exit(1)
