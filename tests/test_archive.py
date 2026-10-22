"""Tests for reading app files out of a repository tarball."""

from __future__ import annotations

import io
import tarfile

import pytest

from repositoryupdater.archive import app_files
from repositoryupdater.exceptions import InvalidArchiveError

TOP = "hassio-addons-app-example-2b0cc78"


def tarball() -> bytes:
    """Return a tarball laid out the way GitHub serves one."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in (TOP, f"{TOP}/example", f"{TOP}/example/translations"):
            archive.addfile(_directory(name))
        for name, content in {
            f"{TOP}/README.md": b"repository readme",
            f"{TOP}/example/config.yaml": b"name: Example",
            f"{TOP}/example/translations/en.yaml": b"english",
            f"{TOP}/examples/config.yaml": b"not the same directory",
        }.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        link = tarfile.TarInfo(f"{TOP}/example/logo.png")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../etc/passwd"
        archive.addfile(link)
    return buffer.getvalue()


def _directory(name: str) -> tarfile.TarInfo:
    """Return a directory entry."""
    member = tarfile.TarInfo(name)
    member.type = tarfile.DIRTYPE
    return member


def test_app_files() -> None:
    """Test only regular files below the app's directory come out."""
    files = app_files("hassio-addons/app-example", tarball(), "example")

    assert files == {
        "config.yaml": b"name: Example",
        "translations/en.yaml": b"english",
    }


@pytest.mark.parametrize("app_target", ["", "."])
def test_app_in_repository_root(app_target: str) -> None:
    """Test an app living in the root of its repository gets every file."""
    files = app_files("hassio-addons/app-example", tarball(), app_target)

    assert files["README.md"] == b"repository readme"
    assert files["example/config.yaml"] == b"name: Example"


def test_unreadable_archive() -> None:
    """Test an archive that is not one fails clearly."""
    with pytest.raises(InvalidArchiveError, match="app-example cannot be read"):
        app_files("hassio-addons/app-example", b"<html>", "example")
