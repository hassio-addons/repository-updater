"""Tests for reading the app list of an apps repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from repositoryupdater.applist import AppEntry, Channel, parse_app_list
from repositoryupdater.exceptions import InvalidAppListError, InvalidChannelError

from .conftest import load_fixture

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion


@pytest.mark.parametrize(
    ("repository", "channel"),
    [
        ("repository", Channel.STABLE),
        ("repository-beta", Channel.BETA),
        ("repository-edge", Channel.EDGE),
    ],
)
def test_real_app_lists(
    repository: str, channel: Channel, snapshot: SnapshotAssertion
) -> None:
    """Test the app lists of the Home Assistant Community Apps parse."""
    app_list = parse_app_list(
        ".apps.yml", load_fixture(f"repositories/{repository}.yml")
    )

    assert app_list.channel is channel
    assert app_list == snapshot


def test_entry_knows_its_directory() -> None:
    """Test each app keeps the directory it is listed under."""
    app_list = parse_app_list(
        ".apps.yml",
        b"""
channel: stable
apps:
  ssh:
    image: ghcr.io/hassio-addons/ssh/{arch}
    repository: hassio-addons/app-ssh
    target: ssh-source
""",
    )

    assert app_list.apps == [
        AppEntry(
            repository_target="ssh",
            image="ghcr.io/hassio-addons/ssh/{arch}",
            repository="hassio-addons/app-ssh",
            app_target="ssh-source",
        )
    ]


def test_legacy_addons_key() -> None:
    """Test an app list from before apps were called apps."""
    app_list = parse_app_list(
        ".addons.yml",
        b"""
channel: beta
addons:
  ssh:
    image: img
    repository: hassio-addons/app-ssh
    target: ssh
""",
    )

    assert [app.repository_target for app in app_list.apps] == ["ssh"]


@pytest.mark.parametrize(
    "content", [b"channel: edge\n", b"channel: edge\napps:\n"], ids=["absent", "empty"]
)
def test_without_apps(content: bytes) -> None:
    """Test a repository without apps yet has an empty list."""
    assert parse_app_list(".apps.yml", content).apps == []


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        (b"channel: [stable", "not valid YAML"),
        (b"- stable", "does not contain a mapping"),
        (b"apps: {}", 'does not declare a "channel"'),
        (b"channel: stable\napps: [ssh]", "its apps are not a mapping"),
        (b"channel: stable\napps:\n  ssh: hello", 'app "ssh" is not a mapping'),
        (
            b"channel: stable\napps:\n  ssh:\n    repository: a/b\n    target: ssh",
            'app "ssh" is missing "image"',
        ),
        (
            b"channel: stable\napps:\n  ssh:\n    image: img\n    target: ssh",
            'app "ssh" is missing "repository"',
        ),
        (
            b"channel: stable\napps:\n  ssh:\n    image: img\n    repository: a/b",
            'app "ssh" is missing "target"',
        ),
    ],
)
def test_unusable_app_list(content: bytes, problem: str) -> None:
    """Test an unusable app list says what is wrong with it."""
    with pytest.raises(InvalidAppListError, match=problem):
        parse_app_list(".apps.yml", content)


def test_unknown_channel() -> None:
    """Test an unknown channel is named in the error."""
    with pytest.raises(InvalidChannelError, match='"nightly"'):
        parse_app_list(".apps.yml", b"channel: nightly\napps: {}")
