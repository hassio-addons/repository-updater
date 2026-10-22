"""Reading the files of an app out of a repository tarball."""

from __future__ import annotations

import io
import tarfile

from .exceptions import InvalidArchiveError


def app_files(repository: str, tarball: bytes, app_target: str) -> dict[str, bytes]:
    """Return every file in an app's directory, by its path inside that directory.

    Everything is read in memory; nothing touches the disk, so a path in the
    archive can never write outside of where it should.
    """
    # GitHub puts the whole repository in one top-level directory, named
    # after the repository and the commit.
    prefix = "" if app_target in {"", "."} else f"{app_target.strip('/')}/"
    files: dict[str, bytes] = {}

    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
            for member in archive:
                _, _, path = member.name.partition("/")
                if not member.isfile() or not path.startswith(prefix):
                    continue

                content = archive.extractfile(member)
                if content is not None:
                    files[path.removeprefix(prefix)] = content.read()
    except (tarfile.TarError, OSError) as exception:
        raise InvalidArchiveError(repository) from exception

    return files
