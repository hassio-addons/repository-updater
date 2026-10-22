"""Command line interface of the Repository Updater."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from repositoryupdater import APP_FULL_NAME, APP_VERSION
from repositoryupdater.cache import cache_path, default_cache_dir
from repositoryupdater.exceptions import RepositoryUpdaterError
from repositoryupdater.github import GitHub
from repositoryupdater.output import Output
from repositoryupdater.updater import Updater

from .async_typer import AsyncTyper

cli = AsyncTyper(
    help=f"{APP_FULL_NAME}.",
    add_completion=False,
    pretty_exceptions_enable=False,
)
output = Output()

# Every option can also come from the environment. The INPUT_* names are what
# GitHub hands a Docker action for its inputs; GitHub sets an input it was not
# given to an empty string, and Click skips those and tries the next name.
Token = Annotated[
    str,
    typer.Option(
        "--token",
        envvar=["INPUT_TOKEN", "GITHUB_TOKEN"],
        prompt="GitHub access token",
        hide_input=True,
        help="GitHub access token.",
        metavar="TOKEN",
        show_default=False,
    ),
]
RepositoryName = Annotated[
    str,
    typer.Option(
        "--repository",
        envvar=["INPUT_REPOSITORY", "GITHUB_REPOSITORY"],
        prompt="Home Assistant Apps repository to update",
        help="The Home Assistant Apps repository to update.",
        metavar="OWNER/NAME",
        show_default=False,
    ),
]
AppFilter = Annotated[
    str | None,
    typer.Option(
        "--app",
        "--addon",
        envvar=["INPUT_APP", "INPUT_ADDON"],
        help="Update a single app. --addon is the deprecated name.",
        metavar="APP",
        show_default=False,
    ),
]
Force = Annotated[
    bool,
    typer.Option(
        "--force",
        envvar="INPUT_FORCE",
        help="Update apps even when they look up to date.",
    ),
]
DryRun = Annotated[
    bool,
    typer.Option(
        "--dry-run",
        envvar="INPUT_DRY_RUN",
        help="Show what would be committed, without committing.",
    ),
]

UseCache = Annotated[
    bool,
    typer.Option(
        "--cache/--no-cache",
        envvar="INPUT_CACHE",
        help="Remember what the apps repository holds, to skip reloading it.",
    ),
]
CacheDir = Annotated[
    Path | None,
    typer.Option(
        "--cache-dir",
        envvar="INPUT_CACHE_DIR",
        help="Where the cache lives. Defaults to ~/.cache/repository-updater.",
        metavar="PATH",
        show_default=False,
    ),
]


def _show_version(value: bool) -> None:
    """Print the version and stop, when asked for it."""
    if value:
        typer.echo(f"{APP_FULL_NAME}, version {APP_VERSION}")
        raise typer.Exit


Version = Annotated[
    bool,
    typer.Option(
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
]


@cli.error_handler(RepositoryUpdaterError)
def _error_handler(error: RepositoryUpdaterError) -> None:
    """Report what stopped the run, and exit with a failure."""
    output.error(str(error))
    sys.exit(1)


# Typer hands every option over as an argument; the version flag does its
# work in its callback and is only here to show up as an option.
@cli.command()
# pylint: disable-next=too-many-arguments
async def update(  # noqa: PLR0913
    *,
    token: Token,
    repository: RepositoryName,
    app: AppFilter = None,
    force: Force = False,
    dry_run: DryRun = False,
    cache: UseCache = True,
    cache_dir: CacheDir = None,
    _version: Version = False,
) -> None:
    """Bring a Home Assistant Apps repository up to date with its apps."""
    output.title(f"{APP_FULL_NAME} {APP_VERSION}")
    path = cache_path(cache_dir or default_cache_dir(), repository) if cache else None

    async with GitHub(token) as github:
        updater = Updater(
            github=github,
            output=output,
            repository_name=repository,
            app_filter=app,
            force=force,
            dry_run=dry_run,
            cache_path=path,
        )
        try:
            await updater.run()
        finally:
            output.end_section()
