"""Tests for the cache of an apps repository."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from repositoryupdater.appconfig import AppDetails
from repositoryupdater.cache import (
    CachedApp,
    cache_path,
    default_cache_dir,
    git_blob_sha,
    read_cache,
    write_cache,
)
from repositoryupdater.github import Commit, Repository

if TYPE_CHECKING:
    from pathlib import Path

CACHED = CachedApp(
    source="hassio-addons/app-ssh",
    config_filename="config.yaml",
    config_sha="2b0cc7881d1da4f356b9e722bd65498584e6d435",
    repository=Repository(
        full_name="hassio-addons/app-ssh",
        html_url="https://github.com/hassio-addons/app-ssh",
        description=None,
        homepage="",
        default_branch="main",
    ),
    version="24.1.7",
    commit=Commit(
        sha="2b0cc7881d1da4f356b9e722bd65498584e6d435",
        message="Release",
        date=datetime(2025, 9, 1, 10, tzinfo=UTC),
    ),
    details=AppDetails(
        name="SSH",
        slug="ssh",
        description="SSH access",
        url=None,
        archs=("aarch64", "amd64"),
    ),
)


def test_round_trip(tmp_path: Path) -> None:
    """Test what gets written comes back the same."""
    path = tmp_path / "deep" / "cache.json"

    write_cache(path, {"ssh": CACHED})

    assert read_cache(path) == {"ssh": CACHED}
    # Readable for whoever saves it, like actions/cache after a root container.
    assert path.stat().st_mode & 0o777 == 0o644
    assert [file.name for file in path.parent.iterdir()] == ["cache.json"]


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"{}",
        b'{"version": 0, "apps": {}}',
        b'{"version": 1, "apps": {"x": {}}}',
    ],
    ids=["garbage", "empty", "older version", "incomplete entry"],
)
def test_unusable_cache(tmp_path: Path, content: bytes) -> None:
    """Test a cache that cannot be used reads as empty instead of failing."""
    path = tmp_path / "cache.json"
    path.write_bytes(content)

    assert read_cache(path) == {}


def test_missing_cache(tmp_path: Path) -> None:
    """Test no cache at all reads as empty."""
    assert read_cache(tmp_path / "missing.json") == {}


def test_unwritable_cache(tmp_path: Path) -> None:
    """Test a cache that cannot be written raises, for the caller to warn about."""
    blocker = tmp_path / "file"
    blocker.write_text("in the way")

    with pytest.raises(OSError, match=r"exists|directory"):
        write_cache(blocker / "cache.json", {})


def test_cache_path(tmp_path: Path) -> None:
    """Test each apps repository gets a file of its own."""
    assert cache_path(tmp_path, "hassio-addons/repository") == (
        tmp_path / "hassio-addons__repository.json"
    )


def test_default_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Test the cache follows XDG_CACHE_HOME, or else lives in ~/.cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert default_cache_dir() == tmp_path / "repository-updater"

    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_cache_dir() == tmp_path / ".cache" / "repository-updater"


def test_git_blob_sha() -> None:
    """Test the blob SHA is the one Git itself gives the content."""
    content = b"name: Example\nversion: 1.0.0\n"

    expected = (
        subprocess.run(
            ["git", "hash-object", "--stdin"],  # noqa: S607
            input=content,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )

    assert git_blob_sha(content) == expected
