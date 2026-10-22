"""Exceptions raised by the GitHub client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repositoryupdater.exceptions import RepositoryUpdaterError

if TYPE_CHECKING:
    from datetime import datetime


class GitHubError(RepositoryUpdaterError):
    """Something went wrong talking to GitHub."""


class GitHubConnectionError(GitHubError):
    """GitHub could not be reached, or did not answer in time."""


class GitHubResponseError(GitHubError):
    """GitHub answered with an error we have no better name for."""

    def __init__(self, message: str, *, status: int) -> None:
        """Initialize with GitHub's message and the HTTP status."""
        super().__init__(message)
        self.status = status


class GitHubAuthenticationError(GitHubResponseError):
    """GitHub rejected the token."""


class GitHubNotFoundError(GitHubResponseError):
    """The repository, ref or file does not exist, or the token cannot see it."""


class GitHubRateLimitError(GitHubResponseError):
    """The rate limit is spent until the reset time."""

    def __init__(self, message: str, *, status: int, reset: datetime) -> None:
        """Initialize with the moment the rate limit resets."""
        super().__init__(f"{message} (resets at {reset:%H:%M:%S} UTC)", status=status)
        self.reset = reset
