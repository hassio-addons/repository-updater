"""Tests for the GitHub client, against recorded GitHub answers."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp
import orjson
import pytest
from yarl import URL

from repositoryupdater import APP_VERSION
from repositoryupdater.github import (
    GitHub,
    GitHubAuthenticationError,
    GitHubConnectionError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubResponseError,
    User,
)

from .conftest import fixture_bytes

if TYPE_CHECKING:
    from aioresponses import aioresponses
    from syrupy.assertion import SnapshotAssertion

API = "https://api.github.com"
APP = f"{API}/repos/hassio-addons/app-ssh"
REPOSITORY = f"{API}/repos/hassio-addons/repository-edge"

# What GitHub sends along with these answers.
JSON = "application/json; charset=utf-8"
RAW = "application/vnd.github.raw+json; charset=utf-8"

HEAD_SHA = "6f30d62e85d40c8971fd46f3508c50eba00d4c3f"
HEAD_TREE = "a45204440e05792e1bdba9853f65ec3c0a0af7f9"


def mock(
    responses: aioresponses, method: str, url: str, fixture: str, **answer: Any
) -> None:
    """Answer a request with a recorded GitHub answer.

    Anything else about the answer, like its status or headers, passes
    straight on to aioresponses.
    """
    answer.setdefault("content_type", JSON)
    responses.add(url, method, body=fixture_bytes(fixture), **answer)


def sent(responses: aioresponses, method: str, url: str) -> list[Any]:
    """Return the decoded JSON bodies sent to a URL."""
    return [
        orjson.loads(call.kwargs["data"])
        for call in responses.requests[(method, URL(url))]
    ]


def author() -> User:
    """Return an account with a private address, to commit with."""
    return User(id=583231, login="octocat", name="The Octocat", email=None)


async def test_user(
    responses: aioresponses, github: GitHub, snapshot: SnapshotAssertion
) -> None:
    """Test the token's account is read from a real answer."""
    mock(responses, "GET", f"{API}/user", "user.json")

    user = await github.user()

    assert user == snapshot
    assert user.commit_name == "The Octocat"
    # octocat keeps their address private.
    assert user.commit_email == "583231+octocat@users.noreply.github.com"


def test_user_without_name() -> None:
    """Test an account without a display name commits with its login."""
    user = User(id=1, login="frenck", name=None, email="frenck@example.com")

    assert user.commit_name == "frenck"
    assert user.commit_email == "frenck@example.com"


async def test_request_headers(responses: aioresponses, github: GitHub) -> None:
    """Test every request authenticates and pins the API version."""
    mock(responses, "GET", f"{API}/user", "user.json")

    await github.user()

    (call,) = responses.requests[("GET", URL(f"{API}/user"))]
    headers = call.kwargs["headers"]
    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["Authorization"] == "Bearer the-token"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert headers["User-Agent"] == f"repository-updater/{APP_VERSION}"


async def test_repository(
    responses: aioresponses, github: GitHub, snapshot: SnapshotAssertion
) -> None:
    """Test a repository is read by its owner and name."""
    mock(responses, "GET", APP, "repository.json")

    repository = await github.repository("hassio-addons/app-ssh")

    assert repository == snapshot
    # GitHub sends an empty string, not null, for a repository without one.
    assert repository.homepage == ""


async def test_releases(
    responses: aioresponses, github: GitHub, snapshot: SnapshotAssertion
) -> None:
    """Test releases are read newest first."""
    mock(responses, "GET", f"{APP}/releases?per_page=100", "releases.json")

    releases = await github.releases("hassio-addons/app-ssh")

    assert [release.tag_name for release in releases] == [
        "v24.1.7",
        "v24.1.6",
        "v24.1.5",
    ]
    assert releases[0] == snapshot


async def test_release_without_notes(responses: aioresponses, github: GitHub) -> None:
    """Test a release whose notes GitHub sends as null."""
    releases = orjson.loads(fixture_bytes("releases.json"))
    releases[0]["body"] = None
    responses.get(f"{APP}/releases?per_page=100", payload=releases)

    (release, *_) = await github.releases("hassio-addons/app-ssh")

    assert release.body is None


async def test_commit(
    responses: aioresponses, github: GitHub, snapshot: SnapshotAssertion
) -> None:
    """Test a tag resolves to the commit it points at."""
    mock(responses, "GET", f"{APP}/commits/v24.1.7", "commit.json")

    commit = await github.commit("hassio-addons/app-ssh", "v24.1.7")

    assert commit == snapshot
    assert commit.sha == "2b0cc7881d1da4f356b9e722bd65498584e6d435"
    assert commit.date == datetime(2026, 10, 1, 21, 25, 37, tzinfo=UTC)


async def test_commit_unknown_sha(responses: aioresponses, github: GitHub) -> None:
    """Test an unknown SHA, a 422 on this endpoint, counts as not found."""
    mock(
        responses,
        "GET",
        f"{APP}/commits/deadbeefdeadbeef",
        "error_unprocessable.json",
        status=422,
    )

    with pytest.raises(GitHubNotFoundError, match="has no commit deadbeefdeadbeef"):
        await github.commit("hassio-addons/app-ssh", "deadbeefdeadbeef")


async def test_commit_other_errors_pass(
    responses: aioresponses, github: GitHub
) -> None:
    """Test only a 422 turns into not found."""
    responses.get(f"{APP}/commits/v24.1.7", status=500)

    with pytest.raises(GitHubResponseError) as exception_info:
        await github.commit("hassio-addons/app-ssh", "v24.1.7")

    assert exception_info.value.status == 500
    assert not isinstance(exception_info.value, GitHubNotFoundError)


async def test_latest_commit(responses: aioresponses, github: GitHub) -> None:
    """Test the newest commit on the default branch is read."""
    mock(responses, "GET", f"{APP}/commits?per_page=1", "commits.json")

    commit = await github.latest_commit("hassio-addons/app-ssh")

    assert commit.sha == "cbebd406f24959a681bb8d7e524b762c7ea3cf99"


async def test_compare(responses: aioresponses, github: GitHub) -> None:
    """Test the commits between two releases come oldest first."""
    mock(responses, "GET", f"{APP}/compare/v24.1.6...v24.1.7", "compare.json")

    commits = await github.compare("hassio-addons/app-ssh", "v24.1.6", "v24.1.7")

    assert [commit.sha[:7] for commit in commits] == [
        "8d8e4f6",
        "c67a30a",
        "c0fa27d",
        "2b0cc78",
    ]


async def test_file(responses: aioresponses, github: GitHub) -> None:
    """Test a file is read raw, at a ref."""
    url = f"{APP}/contents/ssh/config.yaml?ref=v24.1.7"
    mock(responses, "GET", url, "contents_file.yaml", content_type=RAW)

    contents = await github.file(
        "hassio-addons/app-ssh", "ssh/config.yaml", ref="v24.1.7"
    )

    assert contents == fixture_bytes("contents_file.yaml")
    (call,) = responses.requests[("GET", URL(url))]
    assert call.kwargs["headers"]["Accept"] == "application/vnd.github.raw+json"


async def test_file_missing(responses: aioresponses, github: GitHub) -> None:
    """Test a file that does not exist reads as None."""
    mock(
        responses,
        "GET",
        f"{REPOSITORY}/contents/.apps.yml",
        "error_not_found.json",
        status=404,
    )

    assert await github.file("hassio-addons/repository-edge", ".apps.yml") is None


async def test_file_is_a_directory(responses: aioresponses, github: GitHub) -> None:
    """Test a directory reads as None, not as its JSON listing."""
    mock(responses, "GET", f"{REPOSITORY}/contents/.github", "contents_directory.json")

    assert await github.file("hassio-addons/repository-edge", ".github") is None


async def test_tarball_follows_redirect(
    responses: aioresponses, github: GitHub
) -> None:
    """Test a tarball is downloaded from where GitHub redirects to."""
    codeload = (
        "https://codeload.github.com/hassio-addons/app-ssh/legacy.tar.gz/"
        "refs/tags/v24.1.7"
    )
    responses.get(f"{APP}/tarball/v24.1.7", status=302, headers={"Location": codeload})
    responses.get(codeload, body=b"\x1f\x8b tarball", content_type="application/x-gzip")

    tarball = await github.tarball("hassio-addons/app-ssh", "v24.1.7")

    assert tarball == b"\x1f\x8b tarball"


async def test_tree(responses: aioresponses, github: GitHub) -> None:
    """Test every file in a repository is listed, without the directories."""
    url = f"{REPOSITORY}/git/trees/master?recursive=1"
    mock(responses, "GET", url, "git_tree.json")

    paths = await github.tree("hassio-addons/repository-edge", "master")

    assert "ssh/config.yaml" in paths
    assert "actual-budget/translations/en.yaml" in paths
    assert "ssh" not in paths


async def test_tree_truncated(responses: aioresponses, github: GitHub) -> None:
    """Test a listing GitHub cut off is refused, not half used."""
    tree = orjson.loads(fixture_bytes("git_tree.json"))
    tree["truncated"] = True
    responses.get(f"{REPOSITORY}/git/trees/master?recursive=1", payload=tree)

    with pytest.raises(GitHubResponseError, match="too many files"):
        await github.tree("hassio-addons/repository-edge", "master")


def mock_commit_files(responses: aioresponses) -> None:
    """Answer every step of a commit through the Git Data API, but the last."""
    mock(responses, "GET", f"{REPOSITORY}/git/ref/heads/master", "git_ref.json")
    mock(responses, "GET", f"{REPOSITORY}/git/commits/{HEAD_SHA}", "git_commit.json")
    mock(responses, "POST", f"{REPOSITORY}/git/blobs", "git_blob_created.json")
    mock(responses, "POST", f"{REPOSITORY}/git/trees", "git_tree_created.json")
    mock(responses, "POST", f"{REPOSITORY}/git/commits", "git_commit_created.json")


async def test_commit_files(responses: aioresponses, github: GitHub) -> None:
    """Test files are committed on top of the branch through the Git Data API."""
    mock_commit_files(responses)
    mock(
        responses,
        "PATCH",
        f"{REPOSITORY}/git/refs/heads/master",
        "git_ref_updated.json",
    )

    commit = await github.commit_files(
        "hassio-addons/repository-edge",
        branch="master",
        message=":tada: Release of app Example 1.2.0",
        files={"example/config.yaml": b"name: Example\n", "example/logo.png": None},
        author=author(),
    )

    assert commit is not None
    assert commit.sha == "7638417db6d59f3c431d3e1f261cc637155684cd"

    (blob,) = sent(responses, "POST", f"{REPOSITORY}/git/blobs")
    assert base64.b64decode(blob["content"]) == b"name: Example\n"

    (tree,) = sent(responses, "POST", f"{REPOSITORY}/git/trees")
    assert tree == {
        "base_tree": HEAD_TREE,
        "tree": [
            {
                "path": "example/config.yaml",
                "mode": "100644",
                "type": "blob",
                "sha": "3a0f86fb8db8eea7ccbb9a95f325ddbedfb25e15",
            },
            # A path without a blob is deleted.
            {"path": "example/logo.png", "mode": "100644", "type": "blob", "sha": None},
        ],
    }

    (git_commit,) = sent(responses, "POST", f"{REPOSITORY}/git/commits")
    assert git_commit == {
        "message": ":tada: Release of app Example 1.2.0",
        "tree": "cd8274d15fa3ae2ab983129fb037999f264ba9a7",
        "parents": [HEAD_SHA],
        "author": {
            "name": "The Octocat",
            "email": "583231+octocat@users.noreply.github.com",
        },
    }

    (ref,) = sent(responses, "PATCH", f"{REPOSITORY}/git/refs/heads/master")
    assert ref == {"sha": "7638417db6d59f3c431d3e1f261cc637155684cd", "force": False}


async def test_commit_files_without_changes(
    responses: aioresponses, github: GitHub
) -> None:
    """Test nothing is committed when the tree comes out unchanged."""
    mock(responses, "GET", f"{REPOSITORY}/git/ref/heads/master", "git_ref.json")
    mock(responses, "GET", f"{REPOSITORY}/git/commits/{HEAD_SHA}", "git_commit.json")
    mock(responses, "POST", f"{REPOSITORY}/git/blobs", "git_blob_created.json")
    responses.post(f"{REPOSITORY}/git/trees", payload={"sha": HEAD_TREE})

    commit = await github.commit_files(
        "hassio-addons/repository-edge",
        branch="master",
        message="Nothing",
        files={"README.md": b"same"},
        author=author(),
    )

    assert commit is None
    assert ("POST", URL(f"{REPOSITORY}/git/commits")) not in responses.requests


async def test_commit_files_without_files(
    responses: aioresponses, github: GitHub
) -> None:
    """Test committing no files does not even talk to GitHub."""
    commit = await github.commit_files(
        "hassio-addons/repository-edge",
        branch="master",
        message="Nothing",
        files={},
        author=author(),
    )

    assert commit is None
    assert not responses.requests


async def test_commit_files_branch_moved(
    responses: aioresponses, github: GitHub
) -> None:
    """Test a branch someone else moved meanwhile is not overwritten."""
    mock_commit_files(responses)
    mock(
        responses,
        "PATCH",
        f"{REPOSITORY}/git/refs/heads/master",
        "error_not_fast_forward.json",
        status=422,
    )

    with pytest.raises(GitHubResponseError, match="not a fast forward"):
        await github.commit_files(
            "hassio-addons/repository-edge",
            branch="master",
            message="m",
            files={"README.md": b"new"},
            author=author(),
        )


async def test_unauthorized(responses: aioresponses, github: GitHub) -> None:
    """Test a rejected token raises an authentication error with GitHub's words."""
    mock(responses, "GET", f"{API}/user", "error_unauthorized.json", status=401)

    with pytest.raises(GitHubAuthenticationError, match="Bad credentials"):
        await github.user()


async def test_rate_limited(responses: aioresponses, github: GitHub) -> None:
    """Test a spent rate limit says when it resets."""
    mock(
        responses,
        "GET",
        f"{API}/user",
        "error_rate_limited.json",
        status=403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1756720800"},
    )

    with pytest.raises(GitHubRateLimitError, match="resets at 10:00:00") as info:
        await github.user()

    assert info.value.reset == datetime(2025, 9, 1, 10, tzinfo=UTC)


async def test_forbidden_without_rate_limit(
    responses: aioresponses, github: GitHub
) -> None:
    """Test a 403 for a missing permission is not mistaken for a rate limit."""
    mock_commit_files(responses)
    mock(
        responses,
        "PATCH",
        f"{REPOSITORY}/git/refs/heads/master",
        "error_forbidden.json",
        status=403,
        headers={"x-ratelimit-remaining": "4999"},
    )

    with pytest.raises(GitHubResponseError, match="not accessible") as info:
        await github.commit_files(
            "hassio-addons/repository-edge",
            branch="master",
            message="m",
            files={"README.md": b"new"},
            author=author(),
        )

    assert not isinstance(info.value, GitHubRateLimitError)


async def test_not_found(responses: aioresponses, github: GitHub) -> None:
    """Test a 404 names the request that found nothing."""
    url = f"{API}/repos/hassio-addons/does-not-exist-xyz"
    mock(responses, "GET", url, "error_not_found.json", status=404)

    with pytest.raises(
        GitHubNotFoundError,
        match="nothing at GET /repos/hassio-addons/does-not-exist-xyz: Not Found",
    ):
        await github.repository("hassio-addons/does-not-exist-xyz")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"Service unavailable", "Service unavailable"),
        (b"", "HTTP 503"),
        (b'{"errors": []}', "HTTP 503"),
    ],
    ids=["plain text", "empty", "json without message"],
)
async def test_error_without_json_message(
    responses: aioresponses, github: GitHub, body: bytes, message: str
) -> None:
    """Test an error without a JSON message still says something useful."""
    responses.get(f"{API}/user", status=503, body=body)

    with pytest.raises(GitHubResponseError, match=message):
        await github.user()


async def test_invalid_json(responses: aioresponses, github: GitHub) -> None:
    """Test a successful answer that is not JSON raises a response error."""
    responses.get(f"{API}/user", body=b"<html>", content_type="text/html")

    with pytest.raises(GitHubResponseError, match="invalid JSON"):
        await github.user()


@pytest.mark.parametrize(
    "exception",
    [TimeoutError(), aiohttp.ClientConnectionError("boom")],
    ids=["timeout", "connection"],
)
async def test_connection_errors(
    responses: aioresponses, github: GitHub, exception: Exception
) -> None:
    """Test network trouble raises a connection error."""
    responses.get(f"{API}/user", exception=exception)

    with pytest.raises(GitHubConnectionError):
        await github.user()


async def test_own_session_is_closed(responses: aioresponses) -> None:
    """Test a session the client opened itself is closed with it."""
    mock(responses, "GET", f"{API}/user", "user.json")

    async with GitHub("the-token") as github:
        await github.user()
        session = github.session

    assert session is not None
    assert session.closed


async def test_given_session_stays_open(responses: aioresponses) -> None:
    """Test a session handed to the client is left for its owner to close."""
    mock(responses, "GET", f"{API}/user", "user.json")

    async with aiohttp.ClientSession() as session:
        async with GitHub("the-token", session=session) as github:
            await github.user()

        assert not session.closed
