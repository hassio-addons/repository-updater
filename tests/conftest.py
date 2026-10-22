"""Common fixtures and helpers for the Repository Updater tests."""

# pylint: disable=protected-access

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from repositoryupdater.app import App, AppConfig
from repositoryupdater.const import CHANNEL_STABLE

AppFactory = Callable[..., App]


def release(tag: str, *, draft: bool = False, prerelease: bool = False) -> MagicMock:
    """Return a stand-in for a GitHub release."""
    return MagicMock(tag_name=tag, draft=draft, prerelease=prerelease)


def commit(sha: str) -> MagicMock:
    """Return a stand-in for a GitHub commit."""
    return MagicMock(sha=sha)


def mocked(value: object) -> MagicMock:
    """Return a value the tests replaced with a mock, typed as one."""
    assert isinstance(value, MagicMock)
    return value


@pytest.fixture
def app_factory() -> AppFactory:
    """Return a factory for an App whose GitHub repository is mocked.

    Tags resolve to a commit named "sha-<tag>", so a test can see which
    release a commit came from.
    """

    def _factory(
        *,
        channel: str = CHANNEL_STABLE,
        releases: list[MagicMock] | None = None,
        commits: list[MagicMock] | None = None,
    ) -> App:
        app_repository = MagicMock()
        app_repository.full_name = "frenck/app-example"
        app_repository.html_url = "https://github.com/frenck/app-example"
        app_repository.get_releases.return_value = releases or []
        app_repository.get_commits.return_value = commits or []
        app_repository.get_git_ref.side_effect = lambda ref: SimpleNamespace(
            object=SimpleNamespace(sha=f"sha-{ref.removeprefix('tags/')}")
        )
        app_repository.get_commit.side_effect = commit

        app = App(
            MagicMock(),
            Path("/nonexistent"),
            AppConfig(
                repository_target="example",
                image="ghcr.io/frenck/{arch}-example",
                repository="frenck/app-example",
                app_target="example",
                channel=channel,
            ),
            updating=True,
            output=MagicMock(),
        )
        app.app_repository = app_repository

        # Reading the configuration of the latest version is not what these
        # tests are about; skip the network round trip.
        app._fetch_latest_config_file = MagicMock(  # ty: ignore[invalid-assignment]
            return_value=(SimpleNamespace(decoded_content=b"{}"), "config.json")
        )
        app._apply_config = MagicMock()  # ty: ignore[invalid-assignment]
        return app

    return _factory
