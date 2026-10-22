"""Tests for the output module."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from repositoryupdater.output import Output

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


def render(monkeypatch: pytest.MonkeyPatch, *, github_actions: bool) -> str:
    """Return what a typical run prints, without colors."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true" if github_actions else "false")
    buffer = io.StringIO()
    output = Output(Console(file=buffer, width=60, no_color=True, emoji=False))

    output.title("Repository Updater 3.0.0")
    output.info(f"Repository channel: {output.highlight('stable')}")
    output.section(f"App {output.plain('ssh')}")
    output.info(f"Current version: {output.highlight('1.2.0')} (abcdef1)")
    output.warning("This app has an update waiting to be published!")
    output.section(f"App {output.plain('[example]')} {output.highlight('2.0.0')}")
    output.success("This app is up to date.")
    output.end_section()
    output.divider()
    output.step(f"Committing {output.plain(':tada: Release of app [SSH] 1.3.0')}")
    output.done("Done: 1234567")
    output.step("Downloading app source")
    output.failed()
    output.step("Committing README")
    output.skipped()
    output.error("GitHub rejected the token: Bad credentials 100%")

    return buffer.getvalue()


def test_terminal(monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion) -> None:
    """Test how a run looks on a terminal."""
    rendered = render(monkeypatch, github_actions=False)

    assert rendered == snapshot
    # Square brackets in names and emoji shortcodes in messages survive.
    assert ":tada: Release of app [SSH] 1.3.0" in rendered
    assert "App [example] 2.0.0" in rendered
    assert "Error: GitHub rejected the token" in rendered


def test_github_actions(
    monkeypatch: pytest.MonkeyPatch, snapshot: SnapshotAssertion
) -> None:
    """Test every app folds into its own group, and errors become annotations."""
    rendered = render(monkeypatch, github_actions=True)

    assert rendered == snapshot
    assert rendered.count("::group::") == rendered.count("::endgroup::") == 2
    # Group titles are plain text, without markup or escapes.
    assert "::group::App [example] 2.0.0\n" in rendered
    assert "::error::GitHub rejected the token: Bad credentials 100%25" in rendered


def test_end_section_without_section(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test closing a section that is not open prints nothing."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    buffer = io.StringIO()

    Output(Console(file=buffer)).end_section()

    assert buffer.getvalue() == ""


def test_default_console() -> None:
    """Test the output writes to standard output by default."""
    assert Output().console.file is not None


def test_error_closes_an_open_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test an error interrupting a step puts the step to rest first."""
    monkeypatch.setenv("GITHUB_ACTIONS", "false")
    buffer = io.StringIO()
    output = Output(Console(file=buffer, no_color=True))

    output.step("Downloading app source")
    output.error("Archive gone")

    assert (
        buffer.getvalue() == "Downloading app source...Failed!\nError: Archive gone\n"
    )


def test_outside_values_never_break_the_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test a newline in a value cannot start a workflow command of its own."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    buffer = io.StringIO()
    output = Output(Console(file=buffer, no_color=True, width=200))

    output.step(f"Committing {output.plain('Example\n::add-mask::secret')}")
    output.done()

    assert buffer.getvalue() == "Committing Example ::add-mask::secret...Done\n"
