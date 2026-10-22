"""
CLI Module.

Handles CLI for the Repository Updater
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click

from . import APP_FULL_NAME, APP_VERSION
from .exceptions import RepositoryUpdaterError
from .github import GitHub
from .output import Output
from .updater import Updater

if TYPE_CHECKING:
    from collections.abc import Callable


# Every option can also come from the environment. The INPUT_* names are what
# GitHub hands a Docker action for its inputs; GitHub sets an input it was not
# given to an empty string, and Click skips those and tries the next name.
@click.command()
@click.option(
    "--token",
    envvar=["INPUT_TOKEN", "GITHUB_TOKEN"],
    show_envvar=True,
    hide_input=True,
    prompt="GitHub access token",
    help="GitHub access token",
    metavar="<TOKEN>",
)
@click.option(
    "--repository",
    envvar=["INPUT_REPOSITORY", "GITHUB_REPOSITORY"],
    show_envvar=True,
    prompt="Home Assistant Apps repository to update",
    help="The Home Assistant Apps repository to update",
    metavar="<orgname/reponame>",
)
@click.option(
    "--app",
    "--addon",
    "app",
    envvar=["INPUT_APP", "INPUT_ADDON"],
    show_envvar=True,
    help="Update a single/specific app",
    metavar="<TARGET>",
)
@click.option(
    "--force",
    is_flag=True,
    envvar="INPUT_FORCE",
    show_envvar=True,
    help="Force an update of the app repository",
)
@click.option(
    "--dry-run",
    is_flag=True,
    envvar="INPUT_DRY_RUN",
    show_envvar=True,
    help="Show what would be committed, without committing",
)
@click.version_option(APP_VERSION, prog_name=APP_FULL_NAME)
def repository_updater(
    *,
    token: str,
    repository: str,
    app: str | None,
    force: bool,
    dry_run: bool,
) -> None:
    """Home Assistant Community Apps Repository Updater."""
    output = Output()
    output.title(f"{APP_FULL_NAME} {APP_VERSION}")

    def build(github: GitHub) -> Updater:
        return Updater(
            github=github,
            output=output,
            repository_name=repository,
            app_filter=app,
            force=force,
            dry_run=dry_run,
        )

    try:
        asyncio.run(_update(token, build))
    except RepositoryUpdaterError as err:
        raise click.ClickException(str(err)) from err


async def _update(token: str, build: Callable[[GitHub], Updater]) -> None:
    """Run an updater with a GitHub client that is closed afterwards."""
    async with GitHub(token) as github:
        await build(github).run()
