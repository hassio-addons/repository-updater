"""Tests for the command line interface."""

# pylint: disable=redefined-outer-name,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from repositoryupdater import APP_VERSION, cli
from repositoryupdater.exceptions import RepositoryUpdaterError

if TYPE_CHECKING:
    from collections.abc import Generator

    from syrupy.assertion import SnapshotAssertion

ARGS = ["--token", "secret", "--repository", "hassio-addons/repository"]

ENVIRONMENT_VARIABLES = (
    "GITHUB_REPOSITORY",
    "GITHUB_TOKEN",
    "INPUT_ADDON",
    "INPUT_APP",
    "INPUT_DRY_RUN",
    "INPUT_FORCE",
    "INPUT_REPOSITORY",
    "INPUT_TOKEN",
    "GITHUB_ACTIONS",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the environment the tests run in out of the CLI options.

    GitHub Actions sets GITHUB_REPOSITORY and friends for every job, which
    would otherwise fill in options these tests leave out on purpose.
    """
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    # Rich renders the help to the terminal; pin it for the snapshot.
    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def runner() -> CliRunner:
    """Return a runner for invoking the CLI."""
    return CliRunner()


@pytest.fixture
def github() -> Generator[MagicMock]:
    """Replace the GitHub client the CLI opens."""
    with patch.object(cli, "GitHub") as github:
        yield github


@pytest.fixture
def updater() -> Generator[MagicMock]:
    """Replace the updater the CLI runs, keeping what it was given."""
    with patch.object(cli, "Updater") as updater:
        updater.return_value.run = AsyncMock()
        yield updater


def options(updater: MagicMock) -> dict[str, Any]:
    """Return the options the updater was created with."""
    return dict(updater.call_args.kwargs)


def test_version(runner: CliRunner) -> None:
    """Test the version option shows the installed version."""
    result = runner.invoke(cli.cli, ["--version"])

    assert result.exit_code == 0
    assert APP_VERSION in result.output


def test_help(runner: CliRunner, snapshot: SnapshotAssertion) -> None:
    """Test the help output stays as documented."""
    result = runner.invoke(cli.cli, ["--help"], prog_name="repository-updater")

    assert result.exit_code == 0
    assert result.output == snapshot


def test_run(runner: CliRunner, github: MagicMock, updater: MagicMock) -> None:
    """Test a run hands the options to the updater and runs it."""
    result = runner.invoke(cli.cli, [*ARGS, "--app", "example", "--force", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert APP_VERSION in result.output
    github.assert_called_once_with("secret")
    assert options(updater) == {
        "github": github.return_value.__aenter__.return_value,
        "output": options(updater)["output"],
        "repository_name": "hassio-addons/repository",
        "app_filter": "example",
        "force": True,
        "dry_run": True,
    }
    updater.return_value.run.assert_awaited_once_with()


@pytest.mark.usefixtures("github")
def test_addon_is_an_alias_for_app(runner: CliRunner, updater: MagicMock) -> None:
    """Test the deprecated --addon option still selects an app."""
    result = runner.invoke(cli.cli, [*ARGS, "--addon", "example"])

    assert result.exit_code == 0, result.output
    assert options(updater)["app_filter"] == "example"


def test_options_from_github_action_inputs(
    runner: CliRunner, github: MagicMock, updater: MagicMock
) -> None:
    """Test a Docker action run, where every input arrives as INPUT_*.

    GitHub sets inputs that were not given to an empty string, so the
    deprecated addon input and the repository the workflow runs in must
    still be picked up behind them.
    """
    environment = {
        "INPUT_TOKEN": "secret",
        "INPUT_REPOSITORY": "",
        "GITHUB_REPOSITORY": "hassio-addons/repository-edge",
        "INPUT_APP": "",
        "INPUT_ADDON": "example",
        "INPUT_FORCE": "true",
        "INPUT_DRY_RUN": "false",
    }

    result = runner.invoke(cli.cli, [], env=environment)

    assert result.exit_code == 0, result.output
    github.assert_called_once_with("secret")
    assert options(updater)["repository_name"] == "hassio-addons/repository-edge"
    assert options(updater)["app_filter"] == "example"
    assert options(updater)["force"] is True
    assert options(updater)["dry_run"] is False


@pytest.mark.parametrize(
    ("environment", "option", "expected"),
    [
        ({"INPUT_FORCE": "false"}, "force", False),
        ({"INPUT_FORCE": ""}, "force", False),
        ({"INPUT_DRY_RUN": "true"}, "dry_run", True),
        ({"INPUT_APP": "new", "INPUT_ADDON": "old"}, "app_filter", "new"),
        ({"INPUT_TOKEN": "", "GITHUB_TOKEN": "fallback"}, "token", "fallback"),
        ({"INPUT_TOKEN": "input", "GITHUB_TOKEN": "fallback"}, "token", "input"),
    ],
    ids=[
        "force false",
        "force empty",
        "dry run",
        "app over addon",
        "token fallback",
        "token input first",
    ],
)
def test_environment_precedence(
    runner: CliRunner,
    github: MagicMock,
    updater: MagicMock,
    environment: dict[str, str],
    option: str,
    expected: object,
) -> None:
    """Test which environment variable wins when several are set."""
    environment = {
        "INPUT_TOKEN": "secret",
        "GITHUB_REPOSITORY": "hassio-addons/repository",
        **environment,
    }

    result = runner.invoke(cli.cli, [], env=environment)

    assert result.exit_code == 0, result.output
    received = {**options(updater), "token": github.call_args.args[0]}
    assert received[option] == expected


@pytest.mark.usefixtures("github")
def test_command_line_beats_environment(runner: CliRunner, updater: MagicMock) -> None:
    """Test an option given on the command line wins over the environment."""
    result = runner.invoke(
        cli.cli,
        [*ARGS, "--app", "from-argument"],
        env={"INPUT_APP": "from-environment"},
    )

    assert result.exit_code == 0, result.output
    assert options(updater)["app_filter"] == "from-argument"


def run(args: list[str]) -> int | str | None:
    """Run the CLI the way the console script does, and return its exit code.

    The error handlers live in AsyncTyper.__call__, which the CliRunner skips.
    """
    with pytest.raises(SystemExit) as exit_info:
        cli.cli(args, prog_name="repository-updater")
    return exit_info.value.code


def test_error_is_reported(
    github: MagicMock,
    updater: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test an updater error ends the run with its message, and closes GitHub."""
    updater.return_value.run.side_effect = RepositoryUpdaterError("Kaboom")

    assert run(ARGS) == 1
    assert "Error: Kaboom" in capsys.readouterr().out
    github.return_value.__aexit__.assert_awaited_once()


@pytest.mark.usefixtures("github")
def test_error_on_github_actions(
    updater: MagicMock,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test an updater error becomes an annotation on GitHub Actions."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    updater.return_value.run.side_effect = RepositoryUpdaterError("Kaboom\nboom")

    assert run(ARGS) == 1
    assert "::error::Kaboom%0Aboom" in capsys.readouterr().out


@pytest.mark.usefixtures("github")
def test_other_errors_are_not_swallowed(runner: CliRunner, updater: MagicMock) -> None:
    """Test a bug surfaces as itself instead of a tidy error message."""
    updater.return_value.run.side_effect = ZeroDivisionError

    result = runner.invoke(cli.cli, ARGS)

    assert isinstance(result.exception, ZeroDivisionError)


def test_main_module_runs_the_cli() -> None:
    """Test python -m repositoryupdater starts the same command."""
    with patch.object(cli, "cli", MagicMock()) as command:
        runpy.run_module("repositoryupdater", run_name="__main__")

    command.assert_called_once_with()
