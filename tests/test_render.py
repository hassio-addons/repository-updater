"""Tests for the READMEs, changelogs and commit messages an update writes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import orjson
import pytest

from repositoryupdater.appconfig import AppDetails, parse_config
from repositoryupdater.applist import AppEntry, Channel
from repositoryupdater.exceptions import InvalidTemplateError
from repositoryupdater.github import Commit, Release, Repository
from repositoryupdater.render import (
    README_COMMIT_MESSAGE,
    app_template_data,
    commit_message,
    prepend_changelog,
    render_changelog,
    render_template,
    repository_template_data,
)
from repositoryupdater.versions import AppVersion

from .conftest import load_fixture

if TYPE_CHECKING:
    from typing import Any

    from syrupy.assertion import SnapshotAssertion

DATE = datetime(2025, 9, 1, 10, tzinfo=UTC)

SSH = AppEntry(
    repository_target="ssh",
    image="ghcr.io/hassio-addons/ssh/{arch}",
    repository="hassio-addons/app-ssh",
    app_target="ssh",
)


def real_repository() -> Repository:
    """Return the app-ssh repository, as GitHub sends it."""
    return Repository.from_dict(orjson.loads(load_fixture("github/repository.json")))


def real_release() -> Release:
    """Return the newest release of app-ssh, as GitHub sends it."""
    return Release.from_dict(orjson.loads(load_fixture("github/releases.json"))[0])


def real_commit() -> Commit:
    """Return the commit app-ssh v24.1.7 points at, as GitHub sends it."""
    return Commit.from_dict(orjson.loads(load_fixture("github/commit.json")))


def real_details() -> AppDetails:
    """Return the details from the real SSH app configuration."""
    config = parse_config("ssh/config.yaml", load_fixture("github/contents_file.yaml"))
    return AppDetails.from_config("ssh/config.yaml", config)


def commit(sha: str, message: str) -> Commit:
    """Return a commit with a given SHA and message."""
    return Commit(sha=sha, message=message, date=DATE)


def ssh_data(channel: Channel, version: AppVersion) -> dict[str, Any]:
    """Return the template data of the SSH app."""
    return app_template_data(
        entry=SSH,
        channel=channel,
        details=real_details(),
        version=version,
        repository=real_repository(),
    )


def released() -> AppVersion:
    """Return app-ssh v24.1.7, the way stable publishes it."""
    return AppVersion(version="24.1.7", commit=real_commit(), release=real_release())


def test_app_template_data(snapshot: SnapshotAssertion) -> None:
    """Test what an app README template gets to use, for a real release."""
    data = ssh_data(Channel.STABLE, released())

    assert data == snapshot
    assert data["version"] == "v24.1.7"
    assert data["images"]["amd64"] == "ghcr.io/hassio-addons/ssh/amd64"


def test_app_template_data_of_a_commit() -> None:
    """Test a commit shows as its short SHA, dated by the commit."""
    version = AppVersion(version="2b0cc78", commit=real_commit())

    data = ssh_data(Channel.EDGE, version)

    assert data["version"] == "2b0cc78"
    assert data["date"] == real_commit().date
    assert data["channel"] == "edge"


@pytest.mark.parametrize("channel", list(Channel))
def test_render_real_app_readme(channel: Channel, snapshot: SnapshotAssertion) -> None:
    """Test the real README template of the SSH app renders for each channel."""
    template = load_fixture("repositories/app-ssh.README.j2").decode()

    readme = render_template(
        template, ssh_data(channel, released()), location="template"
    )

    assert readme == snapshot


def test_repository_template_data() -> None:
    """Test apps come sorted by name, under both the new and the old name."""
    zebra = {"name": "Zebra"}
    alpha = {"name": "Alpha"}

    data = repository_template_data(
        repository=real_repository(), channel=Channel.BETA, apps=[zebra, alpha]
    )

    assert data["apps"] == [alpha, zebra]
    assert data["addons"] == data["apps"]
    assert data["channel"] == "beta"
    assert data["name"] == "hassio-addons/app-ssh"
    assert data["issues"] == "https://github.com/hassio-addons/app-ssh/issues"


def test_render_real_repository_readme(snapshot: SnapshotAssertion) -> None:
    """Test the real README template of the apps repository renders."""
    template = load_fixture("repositories/repository.README.j2").decode()
    data = repository_template_data(
        repository=real_repository(),
        channel=Channel.STABLE,
        apps=[ssh_data(Channel.STABLE, released())],
    )

    readme = render_template(template, data, location="template")

    assert readme == snapshot
    assert "Advanced SSH & Web Terminal" in readme


def test_changelog_of_a_release() -> None:
    """Test a release brings its own notes."""
    changelog = render_changelog(released())

    assert changelog == real_release().body


def test_changelog_of_a_release_without_notes() -> None:
    """Test a release without notes gets an empty changelog."""
    version = AppVersion(
        version="1.0.0",
        commit=commit("aaa", "Fix"),
        release=Release(
            tag_name="v1.0.0", draft=False, prerelease=False, body=None, created_at=DATE
        ),
    )

    assert render_changelog(version) == ""


def test_changelog_since_release() -> None:
    """Test a commit lists the commits since the last release, newest first."""
    version = AppVersion(version="ccccccc", commit=commit("ccccccccc", "Newest"))

    changelog = render_changelog(
        version,
        since=real_release(),
        commits=[commit("aaa", ":memo: Oldest"), commit("ccccccccc", "Newest")],
    )

    assert changelog == "# Changelog since v24.1.7\n- Newest \n- 📝 Oldest \n"


def test_changelog_without_any_release() -> None:
    """Test a commit with nothing released before shows its own message."""
    version = AppVersion(version="ccccccc", commit=commit("ccccccccc", ":bug: Fix"))

    assert render_changelog(version) == "- 🐛 Fix\n"


@pytest.mark.parametrize(
    ("version", "forced", "expected"),
    [
        (released(), False, ":tada: Release of app SSH 24.1.7"),
        (released(), True, ":tada: Release of app SSH 24.1.7 (forced update)"),
        (
            AppVersion(version="2b0cc78", commit=real_commit()),
            False,
            ":arrow_up: Updating app SSH to 2b0cc78",
        ),
    ],
)
def test_commit_message(
    version: AppVersion,
    forced: bool,  # noqa: FBT001
    expected: str,
) -> None:
    """Test the commit message tells a release from a commit."""
    assert commit_message("SSH", version, forced=forced) == expected


def test_readme_commit_message() -> None:
    """Test the README commit message stays what apps repositories know."""
    assert README_COMMIT_MESSAGE == ":books: Updated README"


def test_prepend_to_empty_changelog() -> None:
    """Test the first notes of an app become its first section."""
    changelog = prepend_changelog("", "- First", version="1.0.0", previous_version=None)

    assert changelog == "## 1.0.0\n\n- First\n"


def test_prepend_above_newest_version() -> None:
    """Test new notes go above the newest version, below the introduction."""
    existing = "# Changelog\n\nAll notable changes.\n\n## 1.0.0\n\n- First\n"

    changelog = prepend_changelog(
        existing, "- Second", version="1.1.0", previous_version="1.0.0"
    )

    assert changelog == (
        "# Changelog\n\nAll notable changes.\n\n"
        "## 1.1.0\n\n- Second\n\n"
        "## 1.0.0\n\n- First\n"
    )


def test_prepend_after_replace_mode() -> None:
    """Test notes left by replace mode get filed under their own version.

    Without that, they would read as part of the new release.
    """
    existing = "## What's changed\n\n- First\n"

    changelog = prepend_changelog(
        existing,
        "## What's changed\n\n- Second",
        version="1.1.0",
        previous_version="1.0.0",
    )

    assert changelog == (
        "## 1.1.0\n\n## What's changed\n\n- Second\n\n"
        "## 1.0.0\n\n## What's changed\n\n- First\n"
    )


def test_prepend_below_title_without_versions() -> None:
    """Test a title without any version yet stays on top."""
    changelog = prepend_changelog(
        "# Changelog\n", "- First", version="1.0.0", previous_version=None
    )

    assert changelog == "# Changelog\n\n## 1.0.0\n\n- First\n"


def test_prepend_rerun_replaces_own_section() -> None:
    """Test a rerun replaces the section of its version, keeping the older ones."""
    existing = "## 1.1.0\n\n- Old\n\n## 1.0.0 (2025-09-01)\n\n- First\n"

    changelog = prepend_changelog(
        existing, "- Fixed", version="1.1.0", previous_version="1.1.0"
    )

    assert changelog == "## 1.1.0\n\n- Fixed\n\n## 1.0.0 (2025-09-01)\n\n- First\n"


def test_prepend_rerun_without_older_versions() -> None:
    """Test a rerun on the only version replaces it entirely."""
    changelog = prepend_changelog(
        "## 1.0.0\n\n- Old\n", "- Fixed", version="1.0.0", previous_version="1.0.0"
    )

    assert changelog == "## 1.0.0\n\n- Fixed\n"


def test_prepend_ignores_numbered_headings() -> None:
    """Test a numbered heading in the notes is not taken for a version."""
    existing = "## 1.0.0\n\n## 2. Known limitations\n\n- Slow\n"

    changelog = prepend_changelog(
        existing, "- Faster", version="1.1.0", previous_version="1.0.0"
    )

    assert changelog == (
        "## 1.1.0\n\n- Faster\n\n## 1.0.0\n\n## 2. Known limitations\n\n- Slow\n"
    )


@pytest.mark.parametrize(
    ("template", "problem"),
    [
        (b"\xff\xfe", "not UTF-8 text"),
        ("{% broken %}", "broken"),
        ("{{ cycler.__init__.__globals__.os.environ }}", "unsafe"),
    ],
    ids=["not text", "syntax", "escaping the sandbox"],
)
def test_template_errors(template: str | bytes, problem: str) -> None:
    """Test a template that cannot render says which one and why."""
    with pytest.raises(InvalidTemplateError, match=f"app/.README.j2 .*{problem}"):
        render_template(template, {}, location="app/.README.j2")
