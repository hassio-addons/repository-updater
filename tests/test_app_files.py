"""Tests for the files an app update writes into the apps repository."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
import yaml
from repositoryupdater.app import App
from repositoryupdater.exceptions import AppConfigNotFoundError, AppNotUpdatingError

from .conftest import commit, mocked

if TYPE_CHECKING:
    from pathlib import Path

    from syrupy.assertion import SnapshotAssertion

    from .conftest import AppFactory

SOURCE_CONFIG = {
    "name": "Example",
    "version": "dev",
    "slug": "example",
    "description": "An example app",
    "url": "https://github.com/frenck/app-example",
    "arch": ["aarch64", "amd64"],
}


@pytest.fixture
def app(app_factory: AppFactory, tmp_path: Path) -> App:
    """Return an app mid-update: a source clone and an apps repository on disk."""
    app = app_factory()

    source = tmp_path / "source"
    (source / "example").mkdir(parents=True)
    app.app_clone = MagicMock(working_dir=str(source))

    app.repository_dir = tmp_path / "repository"
    app.ensure_app_dir()

    app.current_version = "1.2.0"
    app.current_commit = MagicMock(
        sha="0123456789abcdef",
        last_modified="Mon, 01 Sep 2025 10:00:00 GMT",
        commit=MagicMock(message=":bug: Fix the thing"),
    )
    app.current_release = MagicMock(
        tag_name="v1.2.0",
        body="## What's changed\n\n- :sparkles: New thing\n",
        created_at=datetime(2025, 9, 1, 10, tzinfo=UTC),
    )
    app.name = "Example"
    app.description = "An example app"
    app.slug = "example"
    app.url = "https://github.com/frenck/app-example"
    app.archs = ["aarch64", "amd64"]
    return app


@pytest.mark.parametrize("filename", ["config.yaml", "config.json"])
def test_generate_app_config(
    app: App, filename: str, snapshot: SnapshotAssertion
) -> None:
    """Test the app configuration gets the published version and image."""
    source = app.source_dir / filename
    source.write_text(json.dumps(SOURCE_CONFIG), encoding="utf8")
    # A config in another format from an earlier release must not linger.
    (app.target_dir / "config.yml").write_text("old", encoding="utf8")

    app.generate_app_config()

    assert sorted(path.name for path in app.target_dir.glob("config.*")) == [filename]
    written = (app.target_dir / filename).read_text(encoding="utf8")
    assert written == snapshot

    parsed = (
        json.loads(written) if filename.endswith(".json") else yaml.safe_load(written)
    )
    assert parsed["version"] == "1.2.0"
    assert parsed["image"] == "ghcr.io/frenck/{arch}-example"


def test_generate_app_config_without_config(app: App) -> None:
    """Test a source without any app configuration fails clearly."""
    with pytest.raises(AppConfigNotFoundError, match="source/example"):
        app.generate_app_config()


def test_changelog_of_a_release(app: App) -> None:
    """Test a release uses its release notes, with emoji shortcodes expanded."""
    app.generate_app_changelog()

    changelog = (app.target_dir / "CHANGELOG.md").read_text(encoding="utf8")
    assert changelog == "## What's changed\n\n- ✨ New thing\n"


def test_changelog_since_the_last_release(app: App) -> None:
    """Test an edge update lists the commits since the last release."""
    app.latest_is_release = False
    app.latest_release = app.current_release
    mocked(app.app_repository).compare.return_value = SimpleNamespace(
        commits=[
            SimpleNamespace(commit=SimpleNamespace(message="Newest")),
            SimpleNamespace(commit=SimpleNamespace(message=":memo: Oldest")),
        ]
    )

    app.generate_app_changelog()

    mocked(app.app_repository).compare.assert_called_once_with(
        "v1.2.0", "0123456789abcdef"
    )
    changelog = (app.target_dir / "CHANGELOG.md").read_text(encoding="utf8")
    assert changelog == "# Changelog since v1.2.0\n- 📝 Oldest \n- Newest \n"


def test_changelog_without_any_release(app: App) -> None:
    """Test an edge update without releases shows the commit message."""
    app.latest_is_release = False

    app.generate_app_changelog()

    changelog = (app.target_dir / "CHANGELOG.md").read_text(encoding="utf8")
    assert changelog == "- 🐛 Fix the thing\n"


def test_update_static_files(app: App) -> None:
    """Test static files follow the source: copied, replaced or removed."""
    (app.source_dir / "README.md").write_text("new readme", encoding="utf8")
    (app.target_dir / "README.md").write_text("old readme", encoding="utf8")
    (app.target_dir / "logo.png").write_bytes(b"gone upstream")
    (app.source_dir / "translations").mkdir()
    (app.source_dir / "translations" / "en.yaml").write_text("new", encoding="utf8")
    (app.target_dir / "translations" / "nl.yaml").write_text("old", encoding="utf8")

    app.update_static_files()

    assert (app.target_dir / "README.md").read_text(encoding="utf8") == "new readme"
    assert not (app.target_dir / "logo.png").exists()
    assert sorted(p.name for p in (app.target_dir / "translations").iterdir()) == [
        "en.yaml"
    ]


def test_generate_readme(app: App) -> None:
    """Test the app README renders from the template in the source."""
    (app.source_dir / ".README.j2").write_text(
        "# {{ name }} {{ version }}\n"
        "{% for arch in archs %}- {{ images[arch] }}\n{% endfor %}",
        encoding="utf8",
    )

    app.generate_readme()

    assert (app.target_dir / "README.md").read_text(encoding="utf8") == (
        "# Example v1.2.0\n"
        "- ghcr.io/frenck/aarch64-example\n"
        "- ghcr.io/frenck/amd64-example\n"
    )


def test_generate_readme_without_template(app: App) -> None:
    """Test an app without a README template leaves the README alone."""
    app.generate_readme()

    assert not (app.target_dir / "README.md").exists()


def test_template_data(app: App, snapshot: SnapshotAssertion) -> None:
    """Test the data handed to README templates."""
    assert app.get_template_data() == snapshot


def test_template_data_of_an_edge_commit(app: App) -> None:
    """Test a commit version is used as is, dated by the commit."""
    app.current_version = "0123456"
    app.current_release = None

    data = app.get_template_data()

    assert data["version"] == "0123456"
    assert data["date"] == "Mon, 01 Sep 2025 10:00:00 GMT"


def test_template_data_without_version(app: App) -> None:
    """Test an app that was never published has no template data."""
    app.current_version = None

    assert app.get_template_data() == {}


@pytest.mark.parametrize(
    ("current", "latest", "force", "expected"),
    [
        ("1.2.0", "1.2.0", False, False),
        ("1.2.0", "1.3.0", False, True),
        ("1.2.0", "1.2.0", True, True),
    ],
)
def test_needs_update(
    app: App,
    current: str,
    latest: str,
    force: bool,  # noqa: FBT001
    expected: bool,  # noqa: FBT001
) -> None:
    """Test an update is needed for a new version, or when forced."""
    app.current_version = current
    app.latest_version = latest
    app.latest_commit = app.current_commit

    assert app.needs_update(force=force) is expected


def test_needs_update_for_a_new_commit(app: App) -> None:
    """Test edge updates on a new commit, even with the same version string."""
    app.latest_version = app.current_version
    app.latest_commit = commit("fedcba9876543210")

    assert app.needs_update(force=False)


def test_app_left_out_never_updates(app: App) -> None:
    """Test an app outside this run neither needs nor accepts an update."""
    app.updating = False
    app.latest_version = "9.9.9"

    assert not app.needs_update(force=True)
    with pytest.raises(AppNotUpdatingError):
        app.update()
