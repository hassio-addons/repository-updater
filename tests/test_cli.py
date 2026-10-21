"""Tests for the command line interface."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from repositoryupdater import APP_VERSION, cli
from repositoryupdater.exceptions import RepositoryUpdaterError

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

ARGS = ["--token", "secret", "--repository", "hassio-addons/repository"]


ENVIRONMENT_VARIABLES = (
    "GITHUB_REPOSITORY",
    "GITHUB_TOKEN",
    "INPUT_ADDON",
    "INPUT_APP",
    "INPUT_FORCE",
    "INPUT_REPOSITORY",
    "INPUT_TOKEN",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the environment the tests run in out of the CLI options.

    GitHub Actions sets GITHUB_REPOSITORY and friends for every job, which
    would otherwise fill in options these tests leave out on purpose.
    """
    for name in ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    # Click wraps the help to the terminal width; pin it for the snapshot.
    monkeypatch.setenv("COLUMNS", "80")


@pytest.fixture
def runner() -> CliRunner:
    """Return a runner for invoking the CLI."""
    return CliRunner()


def test_version(runner: CliRunner) -> None:
    """Test the version option shows the installed version."""
    result = runner.invoke(cli.repository_updater, ["--version"])

    assert result.exit_code == 0
    assert APP_VERSION in result.output


def test_help(runner: CliRunner, snapshot: SnapshotAssertion) -> None:
    """Test the help output stays as documented."""
    result = runner.invoke(cli.repository_updater, ["--help"])

    assert result.exit_code == 0
    assert result.output == snapshot


def test_run_loads_updates_and_cleans_up(runner: CliRunner) -> None:
    """Test a run hands the options to the repository and cleans up after."""
    with (
        patch.object(cli, "GitHub") as github,
        patch.object(cli, "Repository") as repository,
    ):
        github.return_value.get_user.return_value.name = "Frenck"
        result = runner.invoke(
            cli.repository_updater, [*ARGS, "--app", "example", "--force"]
        )

    assert result.exit_code == 0, result.output
    assert "Authenticated with GitHub as Frenck" in result.output
    github.assert_called_once_with("secret")

    _, kwargs = repository.call_args
    assert repository.call_args.args[1:] == ("hassio-addons/repository", "example")
    assert kwargs["force"] is True

    apps_repository = repository.return_value
    apps_repository.load.assert_called_once_with()
    apps_repository.update.assert_called_once_with()
    apps_repository.cleanup.assert_called_once_with()


def test_addon_is_an_alias_for_app(runner: CliRunner) -> None:
    """Test the deprecated --addon option still selects an app."""
    with patch.object(cli, "GitHub"), patch.object(cli, "Repository") as repository:
        result = runner.invoke(cli.repository_updater, [*ARGS, "--addon", "example"])

    assert result.exit_code == 0, result.output
    assert repository.call_args.args[2] == "example"


def test_options_from_github_action_inputs(runner: CliRunner) -> None:
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
    }

    with (
        patch.object(cli, "GitHub") as github,
        patch.object(cli, "Repository") as repository,
    ):
        result = runner.invoke(cli.repository_updater, [], env=environment)

    assert result.exit_code == 0, result.output
    github.assert_called_once_with("secret")
    assert repository.call_args.args[1:] == (
        "hassio-addons/repository-edge",
        "example",
    )
    assert repository.call_args.kwargs["force"] is True


@pytest.mark.parametrize(
    ("environment", "option", "expected"),
    [
        ({"INPUT_FORCE": "false"}, "force", False),
        ({"INPUT_FORCE": ""}, "force", False),
        ({"INPUT_APP": "new", "INPUT_ADDON": "old"}, "app", "new"),
        ({"INPUT_TOKEN": "", "GITHUB_TOKEN": "fallback"}, "token", "fallback"),
        ({"INPUT_TOKEN": "input", "GITHUB_TOKEN": "fallback"}, "token", "input"),
    ],
    ids=[
        "force false",
        "force empty",
        "app over addon",
        "token fallback",
        "token input first",
    ],
)
def test_environment_precedence(
    runner: CliRunner,
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

    with (
        patch.object(cli, "GitHub") as github,
        patch.object(cli, "Repository") as repository,
    ):
        result = runner.invoke(cli.repository_updater, [], env=environment)

    assert result.exit_code == 0, result.output
    received = {
        "token": github.call_args.args[0],
        "app": repository.call_args.args[2],
        "force": repository.call_args.kwargs["force"],
    }
    assert received[option] == expected


def test_command_line_beats_environment(runner: CliRunner) -> None:
    """Test an option given on the command line wins over the environment."""
    with patch.object(cli, "GitHub"), patch.object(cli, "Repository") as repository:
        result = runner.invoke(
            cli.repository_updater,
            [*ARGS, "--app", "from-argument"],
            env={"INPUT_APP": "from-environment"},
        )

    assert result.exit_code == 0, result.output
    assert repository.call_args.args[2] == "from-argument"


def test_error_is_reported_and_still_cleans_up(runner: CliRunner) -> None:
    """Test an updater error ends the run cleanly, after the cleanup."""
    with patch.object(cli, "GitHub"), patch.object(cli, "Repository") as repository:
        apps_repository = repository.return_value
        apps_repository.update.side_effect = RepositoryUpdaterError("Kaboom")
        result = runner.invoke(cli.repository_updater, ARGS)

    assert result.exit_code == 1
    assert "Error: Kaboom" in result.output
    apps_repository.cleanup.assert_called_once_with()


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Username for 'https://github.com': ", "the-token"),
        ("Password for 'https://the-token@github.com': ", ""),
    ],
)
def test_git_askpass_answers(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    prompt: str,
    expected: str,
) -> None:
    """Test the askpass helper answers the prompts Git asks."""
    monkeypatch.setenv("GIT_USERNAME", "the-token")
    monkeypatch.setenv("GIT_PASSWORD", "")
    monkeypatch.setattr(cli, "argv", ["askpass", prompt])

    with pytest.raises(SystemExit) as exit_info:
        cli.git_askpass()

    assert exit_info.value.code is None
    assert capsys.readouterr().out == f"{expected}\n"


def test_git_askpass_refuses_unknown_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test the askpass helper answers nothing it does not recognize."""
    monkeypatch.setenv("GIT_USERNAME", "the-token")
    monkeypatch.setattr(cli, "argv", ["askpass", "Passphrase for key: "])

    with pytest.raises(SystemExit) as exit_info:
        cli.git_askpass()

    assert exit_info.value.code == 1
    assert capsys.readouterr().out == ""


def test_main_module_runs_the_cli() -> None:
    """Test python -m repositoryupdater starts the same command."""
    with patch.object(cli.repository_updater, "main", MagicMock()) as main:
        runpy.run_module("repositoryupdater", run_name="__main__")

    main.assert_called_once()
