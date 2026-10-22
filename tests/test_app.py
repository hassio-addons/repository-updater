"""Tests for the app module."""

# pylint: disable=protected-access

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from repositoryupdater.app import AppConfig, _is_prerelease
from repositoryupdater.const import CHANNEL_BETA, CHANNEL_EDGE, CHANNEL_STABLE
from repositoryupdater.exceptions import AppReleaseNotFoundError

from .conftest import commit, mocked, release

if TYPE_CHECKING:
    from .conftest import AppFactory


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.3", False),
        ("1.2.3-beta.1", True),
        ("1.2.3-rc1", True),
        # Not semver at all, so there is no prerelease part to find.
        ("2024.1", False),
        ("latest", False),
    ],
)
def test_is_prerelease(version: str, expected: bool) -> None:  # noqa: FBT001
    """Test only a valid semver prerelease part counts as a prerelease."""
    assert _is_prerelease(version) is expected


def test_app_config_from_app_list() -> None:
    """Test an app list entry maps onto the app configuration."""
    config = AppConfig.from_app_list(
        "example",
        {
            "image": "ghcr.io/frenck/{arch}-example",
            "repository": "frenck/app-example",
            "target": "example",
        },
        CHANNEL_BETA,
    )

    assert config == AppConfig(
        repository_target="example",
        image="ghcr.io/frenck/{arch}-example",
        repository="frenck/app-example",
        app_target="example",
        channel=CHANNEL_BETA,
    )


def test_latest_skips_prerelease_on_stable(app_factory: AppFactory) -> None:
    """Test stable ignores a prerelease and takes the release below it."""
    app = app_factory(releases=[release("v2.0.0-beta.1"), release("v1.9.0")])

    app._load_latest_info()

    assert app.latest_version == "1.9.0"
    assert app.latest_release is not None
    assert app.latest_release.tag_name == "v1.9.0"
    assert app.latest_commit is not None
    assert app.latest_commit.sha == "sha-v1.9.0"
    assert app.latest_is_release


def test_latest_skips_release_marked_prerelease(app_factory: AppFactory) -> None:
    """Test stable honors the prerelease flag even on a plain version."""
    app = app_factory(releases=[release("v2.0.0", prerelease=True), release("v1.9.0")])

    app._load_latest_info()

    assert app.latest_version == "1.9.0"


def test_latest_takes_prerelease_on_beta(app_factory: AppFactory) -> None:
    """Test beta publishes a prerelease."""
    app = app_factory(
        channel=CHANNEL_BETA,
        releases=[release("v2.0.0-beta.1"), release("v1.9.0")],
    )

    app._load_latest_info()

    assert app.latest_version == "2.0.0-beta.1"


def test_latest_skips_drafts(app_factory: AppFactory) -> None:
    """Test a draft release is never published, not even on beta."""
    app = app_factory(
        channel=CHANNEL_BETA,
        releases=[release("v2.0.0", draft=True), release("v1.9.0")],
    )

    app._load_latest_info()

    assert app.latest_version == "1.9.0"


def test_latest_accepts_non_semver_tag(app_factory: AppFactory) -> None:
    """Test a tag that is not semver is published as is."""
    app = app_factory(releases=[release("2024.1")])

    app._load_latest_info()

    assert app.latest_version == "2024.1"


@pytest.mark.parametrize(
    "releases",
    [
        [],
        [release("v3.0.0", draft=True), release("v2.0.0-beta.1")],
    ],
    ids=["no releases", "only drafts and prereleases"],
)
def test_latest_without_usable_release(app_factory: AppFactory, releases: list) -> None:
    """Test a channel with nothing to publish fails with a clear error."""
    app = app_factory(releases=releases)

    with pytest.raises(
        AppReleaseNotFoundError,
        match='frenck/app-example has no version to publish on the "stable"',
    ):
        app._load_latest_info()

    # Nothing from a skipped release may leak into the latest state.
    assert app.latest_version is None
    assert app.latest_release is None


def test_latest_on_edge_takes_newer_commit(app_factory: AppFactory) -> None:
    """Test edge publishes the newest commit when it is past the release."""
    app = app_factory(
        channel=CHANNEL_EDGE,
        releases=[release("v1.9.0")],
        commits=[commit("abcdef1234567890")],
    )

    app._load_latest_info()

    assert app.latest_version == "abcdef1"
    assert app.latest_commit is not None
    assert app.latest_commit.sha == "abcdef1234567890"
    assert not app.latest_is_release


def test_latest_on_edge_keeps_release_at_head(app_factory: AppFactory) -> None:
    """Test edge publishes the release when it is the newest commit."""
    app = app_factory(
        channel=CHANNEL_EDGE,
        releases=[release("v1.9.0")],
        commits=[commit("sha-v1.9.0")],
    )

    app._load_latest_info()

    assert app.latest_version == "1.9.0"
    assert app.latest_is_release


def test_latest_on_edge_without_releases(app_factory: AppFactory) -> None:
    """Test edge falls back to the newest commit when nothing is released."""
    app = app_factory(channel=CHANNEL_EDGE, commits=[commit("abcdef1234567890")])

    app._load_latest_info()

    assert app.latest_version == "abcdef1"
    assert not app.latest_is_release


def test_latest_without_release_on_stable_never_reads_commits(
    app_factory: AppFactory,
) -> None:
    """Test only edge looks at commits; stable does not fall back to them."""
    app = app_factory(channel=CHANNEL_STABLE, commits=[commit("abcdef1234567890")])

    with pytest.raises(AppReleaseNotFoundError):
        app._load_latest_info()

    mocked(app.app_repository).get_commits.assert_not_called()
