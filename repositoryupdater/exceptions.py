"""
Exceptions module.

Every failure the updater can describe is raised as a
RepositoryUpdaterError, so the CLI can turn it into a clean error message
instead of dumping a stack trace on the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


class RepositoryUpdaterError(Exception):
    """Base class for every error the Repository Updater raises itself."""


class RepositoryAppListNotFoundError(RepositoryUpdaterError):
    """Raised when the apps repository does not declare an app list."""

    def __init__(self, filenames: Iterable[str]) -> None:
        """Initialize with the filenames that were looked for."""
        super().__init__(
            f"Repository does not contain any of these files: {', '.join(filenames)}"
        )


class InvalidChannelError(RepositoryUpdaterError):
    """Raised when the apps repository declares an unknown release channel."""

    def __init__(self, channel: str) -> None:
        """Initialize with the channel that was declared."""
        super().__init__(f'Channel "{channel}" is not a valid channel identifier')


class AppConfigNotFoundError(RepositoryUpdaterError):
    """Raised when an app has no configuration file where one is expected."""

    def __init__(self, location: str) -> None:
        """Initialize with the location that was searched."""
        super().__init__(f"Could not find an app configuration file in {location}")


class AppNotUpdatingError(RepositoryUpdaterError):
    """Raised when updating an app that was left out of this run."""

    def __init__(self, target: str) -> None:
        """Initialize with the app that was asked to update."""
        super().__init__(f'App "{target}" was not marked for updating this run')
