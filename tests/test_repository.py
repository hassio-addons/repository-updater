"""Tests for the repository module."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import UnknownObjectException
from repositoryupdater import repository as repository_module
from repositoryupdater.exceptions import (
    InvalidChannelError,
    RepositoryAppListNotFoundError,
)
from repositoryupdater.repository import Repository

from .conftest import mocked

if TYPE_CHECKING:
    from pathlib import Path

    from syrupy.assertion import SnapshotAssertion

APP_LIST = b"""
channel: stable
apps:
  example:
    image: ghcr.io/frenck/{arch}-example
    repository: frenck/app-example
    target: example
  other:
    image: ghcr.io/frenck/{arch}-other
    repository: frenck/app-other
    target: other
"""


def not_found(_path: str) -> None:
    """Raise what PyGithub raises for a file that does not exist."""
    raise UnknownObjectException(404)


@pytest.fixture
def repository(tmp_path: Path) -> Repository:
    """Return an apps repository with GitHub mocked and a clone on disk."""
    repository = Repository(
        MagicMock(),
        "hassio-addons/repository",
        None,
        force=False,
        output=MagicMock(),
    )
    repository.github_repository = MagicMock(
        description="Home Assistant Community Apps",
        homepage="https://addons.community",
        issues_url="https://github.com/hassio-addons/repository/issues",
        full_name="hassio-addons/repository",
        html_url="https://github.com/hassio-addons/repository",
    )
    repository.git_repo = MagicMock(working_dir=str(tmp_path))
    repository.channel = "stable"
    return repository


def test_fetch_app_list(repository: Repository) -> None:
    """Test the app list is read from the first name that exists."""
    mocked(repository.github_repository).get_contents.side_effect = lambda path: (
        SimpleNamespace(decoded_content=APP_LIST)
        if path == ".addons.yml"
        else not_found(path)
    )

    app_list = repository._fetch_app_list()

    assert app_list["channel"] == "stable"
    assert list(app_list["apps"]) == ["example", "other"]


def test_fetch_app_list_skips_directories(repository: Repository) -> None:
    """Test a directory carrying an app list name is not taken for one."""
    mocked(repository.github_repository).get_contents.side_effect = lambda path: (
        [SimpleNamespace()]
        if path == ".apps.yml"
        else SimpleNamespace(decoded_content=APP_LIST)
    )

    assert repository._fetch_app_list()["channel"] == "stable"


def test_fetch_app_list_missing(repository: Repository) -> None:
    """Test a repository without an app list fails clearly."""
    mocked(repository.github_repository).get_contents.side_effect = not_found

    with pytest.raises(RepositoryAppListNotFoundError):
        repository._fetch_app_list()


def test_load_apps(repository: Repository) -> None:
    """Test every app in the list is loaded, and the filter decides updating."""
    repository.app_filter = "frenck/app-other"

    with (
        patch.object(repository, "_fetch_app_list") as fetch_app_list,
        patch.object(repository_module, "App") as app_class,
    ):
        import yaml  # noqa: PLC0415

        fetch_app_list.return_value = yaml.safe_load(APP_LIST)
        repository.load_apps()

    assert len(repository.apps) == 2
    updating = [call.kwargs["updating"] for call in app_class.call_args_list]
    assert updating == [False, True]
    app_class.return_value.load.assert_called_with()


def test_load_apps_reads_legacy_addons_key(repository: Repository) -> None:
    """Test an app list using the old "addons" key still works."""
    with (
        patch.object(repository, "_fetch_app_list") as fetch_app_list,
        patch.object(repository_module, "App"),
    ):
        fetch_app_list.return_value = {
            "channel": "beta",
            "addons": {
                "example": {
                    "image": "img",
                    "repository": "frenck/app-example",
                    "target": "example",
                }
            },
        }
        repository.load_apps()

    assert repository.channel == "beta"
    assert len(repository.apps) == 1


def test_load_apps_invalid_channel(repository: Repository) -> None:
    """Test an unknown channel is rejected before any app is loaded."""
    with (
        patch.object(
            repository,
            "_fetch_app_list",
            return_value={"channel": "nightly", "apps": {}},
        ),
        pytest.raises(InvalidChannelError, match='"nightly"'),
    ):
        repository.load_apps()


@pytest.mark.parametrize(
    ("app_filter", "expected"),
    [
        (None, True),
        ("example", True),
        ("frenck/app-example", True),
        ("other", False),
    ],
)
def test_is_selected(
    repository: Repository,
    app_filter: str | None,
    expected: bool,  # noqa: FBT001
) -> None:
    """Test the app filter matches on the target or the source repository."""
    repository.app_filter = app_filter

    assert repository._is_selected("example", "frenck/app-example") is expected


def test_commit_changes(repository: Repository) -> None:
    """Test changes are committed unsigned, with the message given."""
    mocked(repository.git_repo).is_dirty.return_value = True

    assert repository.commit_changes(":books: Updated README")

    mocked(repository.git_repo).git.add.assert_called_once_with(".")
    mocked(repository.git_repo).git.commit.assert_called_once_with(
        "--no-gpg-sign", "-m", ":books: Updated README"
    )


def test_commit_changes_without_changes(repository: Repository) -> None:
    """Test nothing is committed when nothing changed."""
    mocked(repository.git_repo).is_dirty.return_value = False

    assert not repository.commit_changes("Nothing")

    mocked(repository.git_repo).git.commit.assert_not_called()


@pytest.mark.parametrize(
    ("latest_is_release", "force", "message"),
    [
        (True, False, ":tada: Release of app Example 1.2.0"),
        (False, False, ":arrow_up: Updating app Example to 1.2.0"),
        (True, True, ":tada: Release of app Example 1.2.0 (forced update)"),
    ],
)
def test_update_app_commit_message(
    repository: Repository,
    latest_is_release: bool,  # noqa: FBT001
    force: bool,  # noqa: FBT001
    message: str,
) -> None:
    """Test the commit message tells a release from an update."""
    repository.force = force
    app = MagicMock(latest_is_release=latest_is_release, current_version="1.2.0")
    app.name = "Example"

    with (
        patch.object(repository, "generate_readme"),
        patch.object(repository, "commit_changes") as commit_changes,
    ):
        repository.update_app(app)

    app.update.assert_called_once_with()
    commit_changes.assert_called_once_with(message)


def test_update_pushes_only_with_commits(repository: Repository) -> None:
    """Test a run pushes when something was committed, and only then."""
    current = MagicMock()
    current.needs_update.return_value = False
    outdated = MagicMock()
    outdated.needs_update.return_value = True
    repository.apps = [current, outdated]

    with (
        patch.object(repository, "generate_readme"),
        patch.object(repository, "commit_changes", return_value=False),
        patch.object(repository, "update_app", return_value=True) as update_app,
    ):
        repository.update()

    update_app.assert_called_once_with(outdated)
    mocked(repository.git_repo).git.push.assert_called_once_with()


def test_update_without_changes_does_not_push(repository: Repository) -> None:
    """Test a run with nothing to do leaves the remote alone."""
    with (
        patch.object(repository, "generate_readme"),
        patch.object(repository, "commit_changes", return_value=False),
    ):
        repository.update()

    mocked(repository.git_repo).git.push.assert_not_called()


def test_generate_readme(
    repository: Repository, tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Test the repository README renders every published app, sorted."""
    (tmp_path / ".README.j2").write_text(
        "# {{ name }} ({{ channel }})\n\n"
        "{{ description }}\n\n"
        "{% for app in apps %}- [{{ app.name }}]({{ app.repo }}) {{ app.version }}\n"
        "{% endfor %}"
        "{% if addons == apps %}Old templates keep working.\n{% endif %}",
        encoding="utf8",
    )
    zebra, alpha, unpublished = MagicMock(), MagicMock(), MagicMock()
    zebra.get_template_data.return_value = {
        "name": "Zebra",
        "repo": "z",
        "version": "v2",
    }
    alpha.get_template_data.return_value = {
        "name": "Alpha",
        "repo": "a",
        "version": "v1",
    }
    unpublished.get_template_data.return_value = {}
    repository.apps = [zebra, unpublished, alpha]

    repository.generate_readme()

    assert (tmp_path / "README.md").read_text(encoding="utf8") == snapshot


def test_generate_readme_without_template(
    repository: Repository, tmp_path: Path
) -> None:
    """Test a repository without a README template keeps its README."""
    repository.generate_readme()

    assert not (tmp_path / "README.md").exists()


def test_cleanup_removes_every_clone(repository: Repository, tmp_path: Path) -> None:
    """Test cleanup removes the repository clone and those of its apps."""
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    repository.clone_dir = clone_dir
    app = MagicMock()
    repository.apps = [app]

    repository.cleanup()

    assert not clone_dir.exists()
    assert repository.clone_dir is None
    app.cleanup.assert_called_once_with()


def test_cleanup_before_cloning(repository: Repository) -> None:
    """Test cleanup is safe when the run failed before anything was cloned."""
    repository.cleanup()

    assert repository.clone_dir is None
