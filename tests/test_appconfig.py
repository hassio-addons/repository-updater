"""Tests for reading and writing app configuration files."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from repositoryupdater.appconfig import AppDetails, parse_config, render_config
from repositoryupdater.const import DEFAULT_ARCHS
from repositoryupdater.exceptions import InvalidAppConfigError

from .conftest import load_fixture

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

IMAGE = "ghcr.io/hassio-addons/ssh/{arch}"


def test_real_config() -> None:
    """Test the configuration of the SSH app reads into its details."""
    config = parse_config("ssh/config.yaml", load_fixture("github/contents_file.yaml"))

    details = AppDetails.from_config("ssh/config.yaml", config)

    assert details.name == "Advanced SSH & Web Terminal"
    assert details.slug == "ssh"
    assert details.archs == ("aarch64", "amd64")


def test_json_config() -> None:
    """Test a configuration in JSON reads the same."""
    config = parse_config(
        "example/config.json",
        b'{"name": "Example", "slug": "example", "description": "An example"}',
    )

    assert config["slug"] == "example"


def test_details_defaults() -> None:
    """Test an app without architectures or a URL still has details."""
    details = AppDetails.from_config(
        "config.yaml", {"name": "Example", "slug": "example", "description": "Hi"}
    )

    assert details.url is None
    assert details.archs == DEFAULT_ARCHS


@pytest.mark.parametrize("key", ["name", "slug", "description"])
def test_details_missing_key(key: str) -> None:
    """Test a configuration without a required key says which one."""
    config = {"name": "Example", "slug": "example", "description": "Hi"}
    del config[key]

    with pytest.raises(InvalidAppConfigError, match=f'missing "{key}"'):
        AppDetails.from_config("example/config.yaml", config)


@pytest.mark.parametrize(
    ("location", "content", "problem"),
    [
        ("config.json", b"{name", "not valid JSON or YAML"),
        ("config.yaml", b"name: [Example", "not valid JSON or YAML"),
        ("config.yaml", b"- Example", "does not contain a mapping"),
    ],
)
def test_unusable_config(location: str, content: bytes, problem: str) -> None:
    """Test an unusable configuration says what is wrong with it."""
    with pytest.raises(InvalidAppConfigError, match=problem):
        parse_config(location, content)


def test_render_real_config_as_yaml(snapshot: SnapshotAssertion) -> None:
    """Test the published configuration of the SSH app, in its own format."""
    config = parse_config("ssh/config.yaml", load_fixture("github/contents_file.yaml"))

    published = render_config("config.yaml", config, version="24.1.7", image=IMAGE)

    assert published == snapshot
    assert yaml.safe_load(published) == {**config, "version": "24.1.7", "image": IMAGE}


def test_render_config_as_json(snapshot: SnapshotAssertion) -> None:
    """Test a JSON configuration stays JSON, keeping its non-ASCII text."""
    config = {"name": "Café", "version": "dev", "slug": "cafe"}

    published = render_config("config.json", config, version="1.0.0", image=IMAGE)

    assert published == snapshot
    assert "Café" in published


@pytest.mark.parametrize(
    "version",
    ["58899e0", "1e5", "1234567", "0x1F", "true", "null", ".inf"],
)
def test_render_config_quotes_what_yaml_12_reads_otherwise(version: str) -> None:
    """Test a version YAML 1.2 would not read as a string gets quotes.

    The Supervisor reads YAML 1.2, where a short commit SHA like 58899e0 is
    the number 58899.0, while PyYAML writes it without quotes.
    """
    published = render_config("config.yaml", {}, version=version, image=IMAGE)

    assert f"version: '{version}'" in published
    assert yaml.safe_load(published)["version"] == version


@pytest.mark.parametrize("version", ["1.2.3", "v1.2.3", "abcdef1", "0123abc"])
def test_render_config_leaves_plain_strings(version: str) -> None:
    """Test a version every YAML parser reads as a string stays as it was."""
    published = render_config("config.yaml", {}, version=version, image=IMAGE)

    assert f"version: {version}\n" in published
