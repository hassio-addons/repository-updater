"""Tests for picking and naming the version a channel publishes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import orjson
import pytest

from repositoryupdater.applist import Channel
from repositoryupdater.github import Commit, Release
from repositoryupdater.versions import (
    AppVersion,
    display_version,
    is_prerelease,
    needs_update,
    pick_latest,
    pick_release,
    version_refs,
)

from .conftest import load_fixture

DATE = datetime(2025, 9, 1, 10, tzinfo=UTC)


def real_releases() -> list[Release]:
    """Return the releases of app-ssh, as GitHub sends them."""
    return [
        Release.from_dict(data)
        for data in orjson.loads(load_fixture("github/releases.json"))
    ]


def release(tag: str, *, draft: bool = False, prerelease: bool = False) -> Release:
    """Return a release with a given tag."""
    return Release(
        tag_name=tag, draft=draft, prerelease=prerelease, body=None, created_at=DATE
    )


def commit(sha: str) -> Commit:
    """Return a commit with a given SHA."""
    return Commit(sha=sha, message="Fix it", date=DATE)


@pytest.mark.parametrize(
    ("tag", "flagged", "expected"),
    [
        ("v24.1.7", False, False),
        ("v24.1.7", True, True),
        ("v1.2.3-beta.1", False, True),
        ("1.2.3-rc1", False, True),
        # The way Home Assistant itself tags betas.
        ("2024.1.0b1", False, True),
        ("2024.1", False, False),
        # A tag that is a SHA, or something else entirely, is no prerelease.
        ("abcdef1", False, False),
        ("latest", False, False),
    ],
)
def test_is_prerelease(tag: str, flagged: bool, expected: bool) -> None:  # noqa: FBT001
    """Test a prerelease is recognized by its flag or by its tag."""
    assert is_prerelease(release(tag, prerelease=flagged)) is expected


def test_pick_release_from_real_releases() -> None:
    """Test the newest release of app-ssh is picked."""
    picked = pick_release(real_releases(), Channel.STABLE)

    assert picked is not None
    assert picked.tag_name == "v24.1.7"


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        (Channel.STABLE, "v1.9.0"),
        (Channel.BETA, "v2.0.0-beta.1"),
        # Edge publishes commits; for releases it is as strict as stable.
        (Channel.EDGE, "v1.9.0"),
    ],
)
def test_pick_release_per_channel(channel: Channel, expected: str) -> None:
    """Test only beta publishes a prerelease, and nobody publishes a draft."""
    releases = [
        release("v3.0.0", draft=True),
        release("v2.0.0-beta.1"),
        release("v1.9.0"),
    ]

    picked = pick_release(releases, channel)

    assert picked is not None
    assert picked.tag_name == expected


def test_pick_release_without_candidates() -> None:
    """Test a channel without anything to publish picks nothing."""
    releases = [release("v3.0.0", draft=True), release("v2.0.0", prerelease=True)]

    assert pick_release(releases, Channel.STABLE) is None
    assert pick_release([], Channel.BETA) is None


def test_pick_latest_release() -> None:
    """Test stable publishes the release, without the v."""
    latest = pick_latest(
        Channel.STABLE,
        release=release("v1.9.0"),
        release_commit=commit("aaa"),
        head=commit("bbb"),
    )

    assert latest == AppVersion(
        version="1.9.0", commit=commit("aaa"), release=release("v1.9.0")
    )
    assert latest.is_release


def test_pick_latest_edge_past_release() -> None:
    """Test edge publishes the newest commit when it is past the release."""
    latest = pick_latest(
        Channel.EDGE,
        release=release("v1.9.0"),
        release_commit=commit("aaa"),
        head=commit("bbbbbbbbbbbb"),
    )

    assert latest == AppVersion(version="bbbbbbb", commit=commit("bbbbbbbbbbbb"))
    assert not latest.is_release


def test_pick_latest_edge_at_release() -> None:
    """Test edge publishes the release when it is the newest commit."""
    latest = pick_latest(
        Channel.EDGE,
        release=release("v1.9.0"),
        release_commit=commit("aaa"),
        head=commit("aaa"),
    )

    assert latest is not None
    assert latest.version == "1.9.0"
    assert latest.is_release


def test_pick_latest_edge_without_release() -> None:
    """Test edge publishes the newest commit when nothing was released."""
    latest = pick_latest(
        Channel.EDGE, release=None, release_commit=None, head=commit("ccccccccc")
    )

    assert latest == AppVersion(version="ccccccc", commit=commit("ccccccccc"))


def test_pick_latest_nothing() -> None:
    """Test a channel without a release has nothing to publish."""
    assert (
        pick_latest(Channel.STABLE, release=None, release_commit=None, head=None)
        is None
    )
    assert (
        pick_latest(Channel.EDGE, release=None, release_commit=None, head=None) is None
    )


def test_version_refs() -> None:
    """Test a version is looked up as is first, then as a v tag."""
    assert version_refs("24.1.7") == ("24.1.7", "v24.1.7")


@pytest.mark.parametrize(
    ("version", "sha", "expected"),
    [
        ("24.1.7", "2b0cc7881d1da4f356b9e722bd65498584e6d435", "v24.1.7"),
        ("2024.1", "2b0cc7881d1da4f356b9e722bd65498584e6d435", "v2024.1"),
        ("abcdef1", "abcdef1234567890", "abcdef1"),
        # A SHA of only digits is still a SHA, not a version number.
        ("4243100", "42431004d5e6f", "4243100"),
    ],
)
def test_display_version(version: str, sha: str, expected: str) -> None:
    """Test a release shows with a v, and a commit as its short SHA."""
    assert display_version(version, sha) == expected
    assert AppVersion(version=version, commit=commit(sha)).display == expected


def test_needs_update() -> None:
    """Test an update is needed for a new version or commit, or when forced."""
    current = AppVersion(version="1.9.0", commit=commit("aaa"))

    assert not needs_update(current, current, force=False)
    assert needs_update(current, current, force=True)
    assert needs_update(None, current, force=False)
    assert needs_update(current, replace(current, version="2.0.0"), force=False)
    assert needs_update(current, replace(current, commit=commit("bbb")), force=False)
