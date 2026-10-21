"""Tests for the output module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repositoryupdater.output import Output

if TYPE_CHECKING:
    import pytest
    from syrupy.assertion import SnapshotAssertion


def test_output(
    capsys: pytest.CaptureFixture[str], snapshot: SnapshotAssertion
) -> None:
    """Test how a run looks on a terminal without colors."""
    output = Output()

    output.title("Repository Updater")
    output.section("Loading app example")
    output.info(f"Current version: {output.highlight('1.2.0')}")
    output.step("Cloning app repository")
    output.done("Cloned!")
    output.step("Re-generating README.md")
    output.skipped()
    output.step("Committing changes")
    output.failed()
    output.warning("This app has an update waiting to be published!")
    output.divider()
    output.success(f"Updating app {output.emphasis('example')}")

    assert capsys.readouterr().out == snapshot
