"""Tests for Typer with async commands and error handlers."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from repositoryupdater.cli.async_typer import AsyncTyper


class BaseError(Exception):
    """An error with a handler."""


class SpecificError(BaseError):
    """A more specific error, with a handler of its own."""


class ChildError(BaseError):
    """An error only its base class has a handler for."""


def app_raising(exception: Exception | None) -> AsyncTyper:
    """Return an app with one async command that raises an exception."""
    app = AsyncTyper()

    @app.command()
    async def run() -> None:
        if exception is not None:
            raise exception
        typer.echo("ran")

    @app.error_handler(BaseError)
    def base(error: BaseError) -> None:
        typer.echo(f"base handled {error}")

    @app.error_handler(SpecificError)
    def specific(error: SpecificError) -> None:
        typer.echo(f"specific handled {error}")

    return app


def test_async_command() -> None:
    """Test an async command runs to completion."""
    result = CliRunner().invoke(app_raising(None), [])

    assert result.output == "ran\n"


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (SpecificError("x"), "specific handled x\n"),
        (ChildError("y"), "base handled y\n"),
    ],
)
def test_most_specific_handler_wins(
    capsys: pytest.CaptureFixture[str], exception: Exception, expected: str
) -> None:
    """Test a handler for a base class covers subclasses without their own.

    The handlers live in AsyncTyper.__call__, which the CliRunner skips, so
    these tests call the app the way the console script does.
    """
    app_raising(exception)([], prog_name="test")

    assert capsys.readouterr().out == expected


def test_unhandled_error_passes() -> None:
    """Test an error without a handler is raised as is."""
    app = app_raising(ZeroDivisionError())

    with pytest.raises(ZeroDivisionError):
        app([], prog_name="test")


def test_exit_passes() -> None:
    """Test a deliberate exit is never treated as an error."""
    app = app_raising(typer.Exit(3))

    with pytest.raises(SystemExit) as exit_info:
        app([], prog_name="test")

    assert exit_info.value.code == 3
