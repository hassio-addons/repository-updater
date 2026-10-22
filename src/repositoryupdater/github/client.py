"""Asynchronous client for the parts of the GitHub API the updater uses."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Self

import aiohttp
import orjson
from yarl import URL

from repositoryupdater import APP_VERSION

from .exceptions import (
    GitHubAuthenticationError,
    GitHubConnectionError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponseError,
)
from .models import Commit, Release, Repository, User

if TYPE_CHECKING:
    from collections.abc import Mapping

API_URL = URL("https://api.github.com")
API_VERSION = "2022-11-28"

MEDIA_TYPE_JSON = "application/vnd.github+json"
MEDIA_TYPE_RAW = "application/vnd.github.raw+json"

# A tarball of a whole app repository takes longer than an API call.
DOWNLOAD_TIMEOUT_FACTOR = 6


@dataclass
class GitHub:
    """Asynchronous client for the parts of the GitHub API the updater uses."""

    token: str
    request_timeout: float = 10.0
    session: aiohttp.ClientSession | None = None

    _close_session: bool = False

    async def _request(
        self,
        url: URL,
        method: str = "GET",
        *,
        json: object = None,
        accept: str = MEDIA_TYPE_JSON,
        download: bool = False,
    ) -> tuple[str, bytes]:
        """Send a request to GitHub and return the content type and body.

        A download, like a tarball of a whole repository, gets more time
        than an API call. Raises the matching GitHubError for anything but a
        successful answer.
        """
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.token}",
            "User-Agent": f"repository-updater/{APP_VERSION}",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        if self.session is None:
            self.session = aiohttp.ClientSession()
            self._close_session = True

        timeout = self.request_timeout
        if download:
            timeout *= DOWNLOAD_TIMEOUT_FACTOR

        try:
            # The timeout covers reading the body too, so a connection that
            # stalls halfway through cannot hang the run.
            async with (
                asyncio.timeout(timeout),
                self.session.request(
                    method,
                    url,
                    headers=headers,
                    data=orjson.dumps(json) if json is not None else None,
                ) as response,
            ):
                body = await response.read()
        except TimeoutError as exception:
            msg = f"GitHub did not answer {method} {url.path} within {timeout}s"
            raise GitHubConnectionError(msg) from exception
        except aiohttp.ClientError as exception:
            msg = f"Could not talk to GitHub for {method} {url.path}"
            raise GitHubConnectionError(msg) from exception

        _raise_for_status(
            method, url, status=response.status, headers=response.headers, body=body
        )
        return response.content_type, body

    async def _request_json(
        self,
        url: URL,
        method: str = "GET",
        *,
        json: object = None,
    ) -> Any:
        """Send a request to GitHub and return its decoded JSON answer."""
        _, body = await self._request(url, method, json=json)
        try:
            return orjson.loads(body)
        except orjson.JSONDecodeError as exception:
            msg = f"GitHub sent invalid JSON for {method} {url.path}"
            raise GitHubResponseError(msg, status=200) from exception

    async def user(self) -> User:
        """Return the account the token belongs to."""
        return User.from_dict(await self._request_json(API_URL / "user"))

    async def repository(self, repository: str) -> Repository:
        """Return a repository, by its "owner/name"."""
        return Repository.from_dict(await self._request_json(_repo_url(repository)))

    async def releases(self, repository: str) -> list[Release]:
        """Return the releases of a repository, newest first.

        Only the first hundred: enough to find the newest release a channel
        may publish, without paging through years of history.
        """
        data = await self._request_json(
            _repo_url(repository, "releases").with_query(per_page=100)
        )
        return [Release.from_dict(release) for release in data]

    async def commit(self, repository: str, ref: str) -> Commit:
        """Return the commit a ref points to: a SHA, a tag or a branch."""
        try:
            data = await self._request_json(_repo_url(repository, "commits", ref))
        except GitHubResponseError as exception:
            # An unknown SHA is a 422, not a 404, on this endpoint.
            if exception.status != HTTPStatus.UNPROCESSABLE_ENTITY:
                raise
            msg = f"{repository} has no commit {ref}"
            raise GitHubNotFoundError(msg, status=exception.status) from exception
        return Commit.from_dict(data)

    async def latest_commit(self, repository: str) -> Commit:
        """Return the newest commit on the default branch."""
        data = await self._request_json(
            _repo_url(repository, "commits").with_query(per_page=1)
        )
        return Commit.from_dict(data[0])

    async def compare(self, repository: str, base: str, head: str) -> list[Commit]:
        """Return the commits after base up to head, oldest first."""
        data = await self._request_json(
            _repo_url(repository, "compare", f"{base}...{head}")
        )
        return [Commit.from_dict(commit) for commit in data["commits"]]

    async def file(
        self, repository: str, path: str, *, ref: str | None = None
    ) -> bytes | None:
        """Return the contents of a file, or None when there is no such file.

        A directory counts as no file: GitHub lists its contents as JSON
        instead of sending raw contents.
        """
        try:
            url = _repo_url(repository, "contents", *path.split("/"))
            content_type, body = await self._request(
                url.with_query(ref=ref) if ref else url, accept=MEDIA_TYPE_RAW
            )
        except GitHubNotFoundError:
            return None

        if content_type == "application/json":
            return None
        return body

    async def tarball(self, repository: str, ref: str) -> bytes:
        """Return a gzipped tarball of a repository at a ref."""
        _, body = await self._request(
            _repo_url(repository, "tarball", ref), download=True
        )
        return body

    async def commit_files(
        self,
        repository: str,
        *,
        branch: str,
        message: str,
        files: Mapping[str, bytes | None],
        author: User,
    ) -> Commit | None:
        """Commit changed files on top of a branch, without a clone.

        Files map a path to its new contents, or to None to delete it. Every
        file is written as a regular, non-executable file. Returns None when
        the files are already exactly like this, so nothing was committed.

        The branch only moves forward: when someone else moved it in the
        meantime, GitHub refuses the update instead of losing their work.
        """
        if not files:
            return None

        head = await self._request_json(
            _repo_url(repository, "git", "ref", "heads", branch)
        )
        head_sha = head["object"]["sha"]
        head_commit = await self._request_json(
            _repo_url(repository, "git", "commits", head_sha)
        )
        base_tree = head_commit["tree"]["sha"]

        async with asyncio.TaskGroup() as group:
            blobs = {
                path: group.create_task(self._create_blob(repository, content))
                for path, content in files.items()
                if content is not None
            }

        tree = await self._request_json(
            _repo_url(repository, "git", "trees"),
            "POST",
            json={
                "base_tree": base_tree,
                "tree": [
                    {
                        "path": path,
                        "mode": "100644",
                        "type": "blob",
                        "sha": blobs[path].result() if path in blobs else None,
                    }
                    for path in sorted(files)
                ],
            },
        )
        if tree["sha"] == base_tree:
            return None

        commit = await self._request_json(
            _repo_url(repository, "git", "commits"),
            "POST",
            json={
                "message": message,
                "tree": tree["sha"],
                "parents": [head_sha],
                "author": {"name": author.commit_name, "email": author.commit_email},
            },
        )
        await self._request_json(
            _repo_url(repository, "git", "refs", "heads", branch),
            "PATCH",
            json={"sha": commit["sha"], "force": False},
        )
        return Commit.from_dict(commit)

    async def _create_blob(self, repository: str, content: bytes) -> str:
        """Store file contents in a repository and return their SHA."""
        blob = await self._request_json(
            _repo_url(repository, "git", "blobs"),
            "POST",
            json={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        return blob["sha"]

    async def close(self) -> None:
        """Close the session, if this client opened it."""
        if self.session and self._close_session:
            await self.session.close()

    async def __aenter__(self) -> Self:
        """Return the client to use as an async context manager."""
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        """Close the session when leaving the context."""
        await self.close()


def _repo_url(repository: str, *parts: str) -> URL:
    """Return the API URL for a repository, or for a path below it."""
    return API_URL.joinpath("repos", *repository.split("/"), *parts)


def _raise_for_status(
    method: str,
    url: URL,
    *,
    status: int,
    headers: Mapping[str, str],
    body: bytes,
) -> None:
    """Raise the GitHubError matching an unsuccessful answer."""
    if status < HTTPStatus.BAD_REQUEST:
        return

    message = _error_message(body) or f"HTTP {status}"
    request = f"{method} {url.path}"

    if status == HTTPStatus.UNAUTHORIZED:
        msg = f"GitHub rejected the token: {message}"
        raise GitHubAuthenticationError(msg, status=status)

    if (
        status in {HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS}
        and headers.get("x-ratelimit-remaining") == "0"
    ):
        reset = datetime.fromtimestamp(
            int(headers.get("x-ratelimit-reset", "0")), tz=UTC
        )
        msg = f"GitHub rate limit reached on {request}"
        raise GitHubRateLimitError(msg, status=status, reset=reset)

    if status == HTTPStatus.NOT_FOUND:
        msg = f"GitHub has nothing at {request}: {message}"
        raise GitHubNotFoundError(msg, status=status)

    msg = f"GitHub refused {request}: {message}"
    raise GitHubResponseError(msg, status=status)


def _error_message(body: bytes) -> str | None:
    """Return the message GitHub put in an error answer, if any."""
    try:
        data = orjson.loads(body)
    except orjson.JSONDecodeError:
        return body.decode(errors="replace").strip() or None

    if isinstance(data, dict) and isinstance(data.get("message"), str):
        return data["message"]
    return None
