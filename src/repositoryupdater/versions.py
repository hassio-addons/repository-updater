"""Which version of an app a channel publishes, and how to call it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from awesomeversion import AwesomeVersion, AwesomeVersionStrategy

from .applist import Channel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .github import Commit, Release

# Strategies AwesomeVersion uses for real version numbers. A commit SHA comes
# out as UNKNOWN, or as BUILDVER when it happens to be all digits, and
# "latest" or "dev" as SPECIALCONTAINER; none of those have prereleases.
VERSION_STRATEGIES = frozenset(
    {
        AwesomeVersionStrategy.CALVER,
        AwesomeVersionStrategy.PEP440,
        AwesomeVersionStrategy.SEMVER,
        AwesomeVersionStrategy.SIMPLEVER,
    }
)


@dataclass(frozen=True, kw_only=True)
class AppVersion:
    """A version of an app, and the commit it was built from."""

    version: str
    commit: Commit
    # The release this version comes from. None for a commit published
    # straight from the branch, and for a version read back from an apps
    # repository, which does not say where it came from.
    release: Release | None = None

    @property
    def is_release(self) -> bool:
        """Return whether this version comes from a release."""
        return self.release is not None

    @property
    def display(self) -> str:
        """Return the version the way READMEs show it: v1.2.3, or a short SHA."""
        return display_version(self.version, self.commit.sha)


def is_prerelease(release: Release) -> bool:
    """Return whether a release is a prerelease.

    Either GitHub marks it as one, or its tag says so, like 1.2.3-beta.1 or
    2024.1.0b1; the same way Home Assistant reads it.
    """
    if release.prerelease:
        return True

    version = AwesomeVersion(release.tag_name)
    return version.strategy in VERSION_STRATEGIES and version.modifier is not None


def pick_release(releases: Iterable[Release], channel: Channel) -> Release | None:
    """Return the newest release a channel may publish, if there is one.

    Drafts never get published. Prereleases only on the beta channel.
    """
    for release in releases:
        if release.draft:
            continue

        if is_prerelease(release) and channel is not Channel.BETA:
            continue

        return release

    return None


def pick_latest(
    channel: Channel,
    *,
    release: Release | None,
    release_commit: Commit | None,
    head: Commit | None,
) -> AppVersion | None:
    """Return the version a channel publishes now, if there is one.

    Edge publishes the newest commit on the branch, unless that commit is
    the newest release itself; the other channels only publish releases.
    """
    release_sha = release_commit.sha if release_commit else None
    if channel is Channel.EDGE and head is not None and head.sha != release_sha:
        return AppVersion(version=head.sha[:7], commit=head)

    if release is None or release_commit is None:
        return None

    return AppVersion(
        version=release.tag_name.removeprefix("v"),
        commit=release_commit,
        release=release,
    )


def version_refs(version: str) -> tuple[str, ...]:
    """Return the Git refs a published version may be found under, in order.

    A release is tagged with or without a v; an edge version is a short SHA.
    GitHub resolves all of them through the same endpoint.
    """
    return (version, f"v{version}")


def display_version(version: str, sha: str) -> str:
    """Return a version the way READMEs show it.

    A version that is the start of its commit SHA is a commit, shown as is.
    Anything else is a release, shown with a v.
    """
    if sha.startswith(version):
        return version
    return f"v{version}"


def needs_update(
    current: AppVersion | None, latest: AppVersion, *, force: bool
) -> bool:
    """Return whether the apps repository is behind on an app."""
    if force or current is None:
        return True

    return current.version != latest.version or current.commit.sha != latest.commit.sha
