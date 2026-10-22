"""What the updater remembers of an apps repository between runs.

A run for a single app still needs every other app for the README of the
apps repository. The cache holds what the apps repository has of each app,
so those do not need loading again. Every entry is checked against the blob
SHA of the app's configuration before use, so a cache that fell behind only
makes a run slower, never wrong.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from mashumaro.exceptions import MissingField
from mashumaro.mixins.orjson import DataClassORJSONMixin

from .appconfig import AppDetails
from .github import Commit, Repository

# Bump when what the cache holds changes; an older cache is then ignored.
CACHE_VERSION = 1


@dataclass(frozen=True, kw_only=True)
class CachedApp(DataClassORJSONMixin):
    """What the apps repository had of one app."""

    # The "owner/name" the app came from; a new one invalidates the entry.
    source: str
    config_filename: str
    # The blob SHA of the app's configuration in the apps repository.
    config_sha: str
    repository: Repository
    version: str
    commit: Commit
    details: AppDetails


@dataclass(kw_only=True)
class Cache(DataClassORJSONMixin):
    """What the updater remembers of one apps repository."""

    version: int = CACHE_VERSION
    apps: dict[str, CachedApp] = field(default_factory=dict)


def default_cache_dir() -> Path:
    """Return where the cache lives when no place is given."""
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "repository-updater"


def cache_path(cache_dir: Path, repository: str) -> Path:
    """Return the cache file of an apps repository."""
    return cache_dir / f"{repository.replace('/', '__')}.json"


def read_cache(path: Path) -> dict[str, CachedApp]:
    """Return the cached apps, or nothing when there is no usable cache."""
    try:
        cache = Cache.from_json(path.read_bytes())
    except (OSError, ValueError, MissingField):
        return {}

    if cache.version != CACHE_VERSION:
        return {}
    return cache.apps


def write_cache(path: Path, apps: dict[str, CachedApp]) -> None:
    """Write the cache, replacing the old one in one go.

    Writing to a file next to it first means a run that gets cut off leaves
    the old cache, never half a new one. Raises OSError when it cannot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as file:
        file.write(Cache(apps=apps).to_jsonb())

    try:
        # A temporary file is private, but on GitHub Actions the container
        # writes the cache as root and actions/cache saves it as the runner.
        Path(file.name).chmod(0o644)
        Path(file.name).replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            Path(file.name).unlink()


def git_blob_sha(content: bytes) -> str:
    """Return the SHA Git gives a file with this content."""
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()
