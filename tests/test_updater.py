"""Tests for bringing an apps repository up to date."""

# pylint: disable=redefined-outer-name,too-many-instance-attributes

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import yaml

from repositoryupdater.exceptions import (
    AppConfigNotFoundError,
    AppReleaseNotFoundError,
    AppVersionNotFoundError,
    InvalidAppConfigError,
    RepositoryAppListNotFoundError,
)
from repositoryupdater.github import (
    Commit,
    GitHub,
    GitHubNotFoundError,
    Release,
    Repository,
    User,
)
from repositoryupdater.output import Output
from repositoryupdater.updater import Updater

if TYPE_CHECKING:
    from collections.abc import Mapping

DATE = datetime(2025, 9, 1, 10, tzinfo=UTC)

APPS_REPOSITORY = "hassio-addons/repository"
APP_REPOSITORY = "hassio-addons/app-example"

APP_LIST = b"""
channel: stable
apps:
  example:
    image: ghcr.io/hassio-addons/example
    repository: hassio-addons/app-example
    target: example
"""

README_TEMPLATE = (
    b"# {{ name }}\n{% for app in apps %}- {{ app.name }} {{ app.version }}\n"
    b"{% endfor %}"
)


def commit(sha: str, message: str = "Fix it") -> Commit:
    """Return a commit with a given SHA."""
    return Commit(sha=sha, message=message, date=DATE)


def release(tag: str, body: str = "Notes", *, prerelease: bool = False) -> Release:
    """Return a published release."""
    return Release(
        tag_name=tag, draft=False, prerelease=prerelease, body=body, created_at=DATE
    )


def app_config(version: str = "dev", **extra: object) -> bytes:
    """Return the configuration file of the example app."""
    config = {
        "name": "Example",
        "version": version,
        "slug": "example",
        "description": "An example app",
        "arch": ["aarch64", "amd64"],
        **extra,
    }
    return yaml.dump(config, sort_keys=False).encode()


@dataclass
class FakeRepository:
    """A GitHub repository, in memory."""

    name: str
    # The files on the default branch.
    files: dict[str, bytes] = field(default_factory=dict)
    releases: list[Release] = field(default_factory=list)
    # Every ref GitHub resolves: SHAs and tags.
    refs: dict[str, Commit] = field(default_factory=dict)
    head: Commit | None = None
    # The files at a commit, by its SHA.
    snapshots: dict[str, dict[str, bytes]] = field(default_factory=dict)
    compares: dict[tuple[str, str], list[Commit]] = field(default_factory=dict)
    branch: str = "main"

    @property
    def info(self) -> Repository:
        """Return the repository the way the API describes it."""
        return Repository(
            full_name=self.name,
            html_url=f"https://github.com/{self.name}",
            description=f"The {self.name} repository",
            homepage="",
            default_branch=self.branch,
        )

    def publish(
        self, sha: str, files: Mapping[str, bytes], tag: str | None = None
    ) -> None:
        """Add a commit with the given files, tagged when a tag is given."""
        self.refs[sha] = self.head = commit(sha, f"Commit {sha[:7]}")
        self.snapshots[sha] = dict(files)
        if tag is not None:
            self.refs[tag] = self.refs[sha]


@dataclass
class Committed:
    """One commit the updater made."""

    message: str
    files: dict[str, bytes | None]


class FakeGitHub(GitHub):
    """The GitHub client, answering from repositories in memory."""

    def __init__(self, *repositories: FakeRepository) -> None:
        """Initialize with the repositories GitHub knows."""
        super().__init__("token")
        self.repositories = {repository.name: repository for repository in repositories}
        self.commits: list[Committed] = []

    def _get(self, name: str) -> FakeRepository:
        if name not in self.repositories:
            msg = f"No repository {name}"
            raise GitHubNotFoundError(msg, status=404)
        return self.repositories[name]

    async def user(self) -> User:
        """Return the account committing."""
        return User(id=583231, login="octocat", name="The Octocat", email=None)

    async def repository(self, repository: str) -> Repository:
        """Return a repository."""
        return self._get(repository).info

    async def file(
        self, repository: str, path: str, *, ref: str | None = None
    ) -> bytes | None:
        """Return a file on the branch, or at a commit."""
        fake = self._get(repository)
        files = fake.snapshots[ref] if ref else fake.files
        return files.get(path)

    async def releases(self, repository: str) -> list[Release]:
        """Return the releases, newest first."""
        return self._get(repository).releases

    async def commit(self, repository: str, ref: str) -> Commit:
        """Return the commit a ref points at."""
        refs = self._get(repository).refs
        if ref not in refs:
            msg = f"No commit {ref}"
            raise GitHubNotFoundError(msg, status=422)
        return refs[ref]

    async def latest_commit(self, repository: str) -> Commit:
        """Return the newest commit on the branch."""
        head = self._get(repository).head
        assert head is not None
        return head

    async def compare(self, repository: str, base: str, head: str) -> list[Commit]:
        """Return the commits between two refs."""
        return self._get(repository).compares[(base, head)]

    async def tree(self, repository: str, ref: str) -> list[str]:
        """Return every file on the branch."""
        fake = self._get(repository)
        assert ref == fake.branch
        return sorted(fake.files)

    async def tarball(self, repository: str, ref: str) -> bytes:
        """Return the files at a commit, packed the way GitHub does."""
        fake = self._get(repository)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for path, content in fake.snapshots[ref].items():
                member = tarfile.TarInfo(
                    f"{fake.name.replace('/', '-')}-{ref[:7]}/{path}"
                )
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        return buffer.getvalue()

    async def commit_files(
        self,
        repository: str,
        *,
        branch: str,
        message: str,
        files: Mapping[str, bytes | None],
        author: User,
    ) -> Commit | None:
        """Apply the files to the branch, the way the Git Data API would."""
        fake = self._get(repository)
        assert branch == fake.branch
        assert author.login == "octocat"

        changed = {
            path: content
            for path, content in files.items()
            if fake.files.get(path) != content
        }
        if not changed:
            return None

        for path, content in changed.items():
            if content is None:
                fake.files.pop(path, None)
            else:
                fake.files[path] = content

        self.commits.append(Committed(message=message, files=dict(files)))
        return commit(f"{len(self.commits):040d}", message)


@pytest.fixture
def app_repository() -> FakeRepository:
    """Return the example app, with release v1.0.0 published and v1.1.0 out."""
    app = FakeRepository(name=APP_REPOSITORY)
    app.publish(
        "1" * 40,
        {"example/config.yaml": app_config(), "example/logo.png": b"old logo"},
        tag="v1.0.0",
    )
    app.publish(
        "2" * 40,
        {
            "example/config.yaml": app_config(),
            "example/icon.png": b"icon",
            "example/DOCS.md": b"Docs",
            "example/translations/en.yaml": b"english",
            "example/.README.j2": b"# {{ name }} {{ version }} on {{ channel }}\n",
        },
        tag="v1.1.0",
    )
    app.releases = [release("v1.1.0", ":tada: Shiny"), release("v1.0.0")]
    return app


@pytest.fixture
def apps_repository() -> FakeRepository:
    """Return an apps repository that holds the example app at v1.0.0."""
    return FakeRepository(
        name=APPS_REPOSITORY,
        files={
            ".apps.yml": APP_LIST,
            ".README.j2": README_TEMPLATE,
            "README.md": b"# hassio-addons/repository\n- Example v1.0.0\n",
            "example/config.yaml": app_config("1.0.0"),
            "example/logo.png": b"old logo",
            "example/translations/nl.yaml": b"dutch",
        },
    )


def only_commit(github: FakeGitHub) -> Committed:
    """Return the one commit the updater made."""
    assert len(github.commits) == 1
    return github.commits[0]


def updater(
    github: FakeGitHub,
    *,
    app_filter: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> Updater:
    """Return an updater for the apps repository."""
    return Updater(
        github=github,
        output=Output(),
        repository_name=APPS_REPOSITORY,
        app_filter=app_filter,
        force=force,
        dry_run=dry_run,
    )


async def test_publishes_a_release(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a new release lands in the apps repository as one commit."""
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    published = only_commit(github)
    assert published.message == ":tada: Release of app Example 1.1.0"

    files = apps_repository.files
    config = yaml.safe_load(files["example/config.yaml"])
    assert config["version"] == "1.1.0"
    assert config["image"] == "ghcr.io/hassio-addons/example"
    assert files["example/icon.png"] == b"icon"
    assert files["example/DOCS.md"] == b"Docs"
    # Gone upstream, so gone here.
    assert "example/logo.png" not in files
    assert files["example/translations/en.yaml"] == b"english"
    assert "example/translations/nl.yaml" not in files
    # Jinja drops the newline that ends a template, like it always did.
    assert files["example/README.md"] == b"# Example v1.1.0 on stable"
    assert files["example/CHANGELOG.md"] == "🎉 Shiny".encode()
    assert files["README.md"] == b"# hassio-addons/repository\n- Example v1.1.0\n"


async def test_readme_copied_without_template(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an app without a README template has its README.md copied."""
    snapshot = app_repository.snapshots["2" * 40]
    del snapshot["example/.README.j2"]
    snapshot["example/README.md"] = b"Handwritten"

    await updater(FakeGitHub(apps_repository, app_repository)).run()

    assert apps_repository.files["example/README.md"] == b"Handwritten"


async def test_up_to_date(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test nothing is committed when the apps repository is current."""
    github = FakeGitHub(apps_repository, app_repository)
    await updater(github).run()

    rerun = FakeGitHub(apps_repository, app_repository)
    await updater(rerun).run()

    assert not rerun.commits


async def test_forced_update_without_changes(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a forced update of a current app has nothing to commit."""
    await updater(FakeGitHub(apps_repository, app_repository)).run()

    github = FakeGitHub(apps_repository, app_repository)
    await updater(github, force=True).run()

    assert not github.commits


async def test_readme_catches_up_first(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a README that fell behind gets its own commit before any update."""
    apps_repository.files["README.md"] = b"outdated"
    app_repository.releases = [release("v1.0.0")]
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    readme = only_commit(github)
    assert readme.message == ":books: Updated README"
    assert readme.files == {
        "README.md": b"# hassio-addons/repository\n- Example v1.0.0\n"
    }


async def test_without_readme_template(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an apps repository without a README template keeps its README."""
    del apps_repository.files[".README.j2"]
    apps_repository.files["README.md"] = b"handwritten"
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    assert apps_repository.files["README.md"] == b"handwritten"
    assert "README.md" not in github.commits[0].files


async def test_edge_publishes_a_commit(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test edge publishes the newest commit, listing what changed since."""
    apps_repository.files[".apps.yml"] = APP_LIST.replace(b"stable", b"edge")
    app_repository.publish(
        "3" * 40, app_repository.snapshots["2" * 40] | {"example/DOCS.md": b"New"}
    )
    app_repository.compares[("v1.1.0", "3" * 40)] = [
        commit("a" * 40, ":memo: Older"),
        commit("3" * 40, "Newer"),
    ]
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    published = only_commit(github)
    assert published.message == ":arrow_up: Updating app Example to 3333333"
    files = apps_repository.files
    assert yaml.safe_load(files["example/config.yaml"])["version"] == "3333333"
    assert files["example/DOCS.md"] == b"New"
    assert files["example/CHANGELOG.md"] == (
        "# Changelog since v1.1.0\n- Newer \n- 📝 Older \n".encode()
    )
    assert files["example/README.md"] == b"# Example 3333333 on edge"


async def test_edge_without_any_release(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test edge publishes a commit of an app that never released."""
    apps_repository.files[".apps.yml"] = APP_LIST.replace(b"stable", b"edge")
    app_repository.releases = []
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    changelog = apps_repository.files["example/CHANGELOG.md"]
    assert changelog == b"- Commit 2222222\n"


async def test_new_app(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an app the apps repository never held gets added."""
    for path in list(apps_repository.files):
        if path.startswith("example/"):
            del apps_repository.files[path]
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    # The README drops the app it no longer finds, then gets it back.
    assert [published.message for published in github.commits] == [
        ":books: Updated README",
        ":tada: Release of app Example 1.1.0",
    ]
    assert b"- Example v1.1.0" in apps_repository.files["README.md"]


async def test_switches_config_format(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an app moving to another config format leaves no old one behind."""
    snapshot = app_repository.snapshots["2" * 40]
    snapshot["example/config.json"] = (
        b'{"name": "Example", "version": "dev", "slug": "example", '
        b'"description": "An example app"}'
    )
    del snapshot["example/config.yaml"]
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github).run()

    assert "example/config.yaml" not in apps_repository.files
    assert b'"version": "1.1.0"' in apps_repository.files["example/config.json"]


async def test_only_the_selected_app(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an app outside the filter is shown, but never looked up or updated."""
    apps_repository.files[".apps.yml"] = APP_LIST + (
        b"  other:\n"
        b"    image: ghcr.io/hassio-addons/other\n"
        b"    repository: hassio-addons/app-other\n"
        b"    target: other\n"
    )
    apps_repository.files["other/config.yaml"] = app_config(
        "2.0.0", name="Other", slug="other"
    )
    apps_repository.files["README.md"] += b"- Other v2.0.0\n"
    other = FakeRepository(name="hassio-addons/app-other")
    other.publish("4" * 40, {}, tag="v2.0.0")
    # A release the filter must not publish.
    other.releases = [release("v9.9.9")]
    github = FakeGitHub(apps_repository, app_repository, other)

    await updater(github, app_filter="example").run()

    assert [published.message for published in github.commits] == [
        ":tada: Release of app Example 1.1.0"
    ]
    assert b"- Other v2.0.0" in apps_repository.files["README.md"]


async def test_dry_run(
    apps_repository: FakeRepository,
    app_repository: FakeRepository,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test a dry run shows what would change, and changes nothing."""
    before = dict(apps_repository.files)
    github = FakeGitHub(apps_repository, app_repository)

    await updater(github, dry_run=True).run()

    assert not github.commits
    assert apps_repository.files == before
    output = capsys.readouterr().out
    assert "Committing :books: Updated README...Skipped, no changes." in output
    assert "Would commit (dry run):" in output
    assert "  add: example/icon.png" in output
    assert "  change: example/config.yaml" in output
    assert "  delete: example/logo.png" in output
    # Deleting what is not there is no change.
    assert "apparmor.txt" not in output


async def test_legacy_app_list_name(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an app list under its old name is found."""
    apps_repository.files[".addons.yml"] = apps_repository.files.pop(".apps.yml")

    await updater(FakeGitHub(apps_repository, app_repository)).run()

    assert (
        yaml.safe_load(apps_repository.files["example/config.yaml"])["version"]
        == "1.1.0"
    )


async def test_without_app_list(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an apps repository without an app list fails clearly."""
    del apps_repository.files[".apps.yml"]

    with pytest.raises(RepositoryAppListNotFoundError):
        await updater(FakeGitHub(apps_repository, app_repository)).run()


async def test_invalid_app_list(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test an unusable app list stops the run before anything else."""
    apps_repository.files[".apps.yml"] = b"apps: {}"
    github = FakeGitHub(apps_repository, app_repository)

    with pytest.raises(Exception, match='does not declare a "channel"'):
        await updater(github).run()

    assert not github.commits


async def test_current_version_unknown(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a version the app repository does not know fails clearly."""
    apps_repository.files["example/config.yaml"] = app_config("0.0.1")

    with pytest.raises(AppVersionNotFoundError, match=r"version 0\.0\.1"):
        await updater(FakeGitHub(apps_repository, app_repository)).run()


async def test_current_config_without_version(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a published configuration without a version fails clearly."""
    config = yaml.safe_load(app_config())
    del config["version"]
    apps_repository.files["example/config.yaml"] = yaml.dump(config).encode()

    with pytest.raises(InvalidAppConfigError, match='missing "version"'):
        await updater(FakeGitHub(apps_repository, app_repository)).run()


async def test_nothing_to_publish(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a channel without a release to publish fails clearly."""
    app_repository.releases = [release("v2.0.0-beta.1")]

    with pytest.raises(AppReleaseNotFoundError, match='on the "stable" channel'):
        await updater(FakeGitHub(apps_repository, app_repository)).run()


async def test_release_without_config(
    apps_repository: FakeRepository, app_repository: FakeRepository
) -> None:
    """Test a release without an app configuration fails clearly."""
    del app_repository.snapshots["2" * 40]["example/config.yaml"]

    with pytest.raises(AppConfigNotFoundError, match="app-example/example at 2222222"):
        await updater(FakeGitHub(apps_repository, app_repository)).run()
