"""Models for the parts of the GitHub API the updater reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mashumaro.mixins.orjson import DataClassORJSONMixin


@dataclass(frozen=True, kw_only=True)
class User(DataClassORJSONMixin):
    """The account the token belongs to."""

    id: int
    login: str
    name: str | None
    email: str | None

    @property
    def commit_name(self) -> str:
        """Return the name to commit with."""
        return self.name or self.login

    @property
    def commit_email(self) -> str:
        """Return an address to commit with, even when the real one is private."""
        return self.email or f"{self.id}+{self.login}@users.noreply.github.com"


@dataclass(frozen=True, kw_only=True)
class Repository(DataClassORJSONMixin):
    """A GitHub repository."""

    full_name: str
    html_url: str
    description: str | None
    homepage: str | None
    default_branch: str


@dataclass(frozen=True, kw_only=True)
class Release(DataClassORJSONMixin):
    """A release of a repository, drafts included."""

    tag_name: str
    draft: bool
    prerelease: bool
    # GitHub sends null for a release without notes.
    body: str | None
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class Commit(DataClassORJSONMixin):
    """A commit, from either the REST API or the Git Data API."""

    sha: str
    message: str
    date: datetime

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        """Flatten the two shapes GitHub uses for a commit.

        The REST API nests the Git commit under "commit"; the Git Data API
        returns the Git commit itself. A commit this model wrote itself, like
        in the cache, is flat already.
        """
        if "date" in d:
            return d

        git_commit = d.get("commit", d)
        return {
            "sha": d["sha"],
            "message": git_commit["message"],
            "date": git_commit["committer"]["date"],
        }
