"""The READMEs, changelogs and commit messages an update writes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import emoji
from jinja2 import BaseLoader, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from .exceptions import InvalidTemplateError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .appconfig import AppDetails
    from .applist import AppEntry, Channel
    from .github import Commit, Release, Repository
    from .versions import AppVersion

README_COMMIT_MESSAGE = ":books: Updated README"

# The heading of a version section in a changelog, like "## 1.2.0" or
# "## v1.2.0 (2025-09-01)", but not a numbered heading like "## 2. Notes".
VERSION_HEADING = re.compile(r"^## v?\d+\.\d+", re.MULTILINE)


def render_template(
    template: str | bytes, data: Mapping[str, Any], *, location: str
) -> str:
    """Render a README template.

    Templates come from the repositories of the apps, so they render in a
    sandbox: a template gets the data it is given, and nothing of the
    process running it, like its environment or the token in there.
    """
    # Autoescaping is off on purpose: these templates render Markdown.
    environment = SandboxedEnvironment(
        loader=BaseLoader(),
        trim_blocks=True,
        extensions=["jinja2.ext.loopcontrols"],
    )
    try:
        text = template.decode() if isinstance(template, bytes) else template
        return environment.from_string(text).render(**data)
    except UnicodeDecodeError as exception:
        msg = "it is not UTF-8 text"
        raise InvalidTemplateError(location, msg) from exception
    except TemplateError as exception:
        raise InvalidTemplateError(location, str(exception)) from exception


def app_template_data(
    *,
    entry: AppEntry,
    channel: Channel,
    details: AppDetails,
    version: AppVersion,
    repository: Repository,
) -> dict[str, Any]:
    """Return what an app README template, and the repository one, get to use.

    These names are a contract with every template out there; keep them.
    """
    return {
        "name": details.name,
        "channel": str(channel),
        "description": details.description,
        "url": details.url,
        "repo": repository.html_url,
        "repo_slug": repository.full_name,
        "archs": list(details.archs),
        "slug": details.slug,
        "target": entry.repository_target,
        "image": entry.image,
        "images": {arch: entry.image.replace("{arch}", arch) for arch in details.archs},
        "version": version.display,
        "commit": version.commit.sha,
        # The commit date, not the release date: a version read back from
        # the apps repository does not know its release, and the README
        # should not change between runs because of that.
        "date": version.commit.date,
    }


def repository_template_data(
    *,
    repository: Repository,
    channel: Channel,
    apps: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return what the README template of an apps repository gets to use.

    These names are a contract with every template out there; keep them.
    """
    apps_by_name = sorted(apps, key=lambda app: app["name"])
    return {
        "apps": apps_by_name,
        # Templates from before apps were called apps.
        "addons": apps_by_name,
        "channel": str(channel),
        "description": repository.description,
        "homepage": repository.homepage,
        "issues": f"{repository.html_url}/issues",
        "name": repository.full_name,
        "repo": repository.html_url,
    }


def render_changelog(
    version: AppVersion,
    *,
    since: Release | None = None,
    commits: Sequence[Commit] = (),
) -> str:
    """Return the changelog an apps repository shows for a version.

    A release brings its own notes. A commit published from the branch gets
    the commits since the last release, newest first, or just its own
    message when nothing was released yet. Emoji shortcodes are expanded.
    """
    if version.release is not None:
        changelog = version.release.body or ""
    elif since is not None:
        changelog = f"# Changelog since {since.tag_name}\n"
        changelog += "".join(f"- {commit.message} \n" for commit in reversed(commits))
    else:
        changelog = f"- {version.commit.message}\n"

    return emoji.emojize(changelog, language="alias")


def prepend_changelog(
    existing: str, notes: str, *, version: str, previous_version: str | None
) -> str:
    """Return a changelog with the notes of a release on top.

    The notes go under a "## <version>" heading above the newest version,
    below any title or introduction. A rerun or a forced update replaces the
    section of its own version. A changelog written in replace mode holds
    the notes of one release without a heading; those get filed under the
    version they belong to. Home Assistant uses these headings to show what
    changed between the installed and the new version.
    """
    newest = VERSION_HEADING.search(existing)
    if newest:
        intro, older = existing[: newest.start()], existing[newest.start() :]
    else:
        intro, older = "", existing
        if older.startswith("# "):
            intro, _, older = older.partition("\n")
            intro += "\n\n"

        if older.strip() and previous_version:
            older = f"## {previous_version}\n\n{older.strip()}\n"

    heading = f"## {version}"
    if older.startswith(f"{heading}\n"):
        next_heading = VERSION_HEADING.search(older, len(heading))
        older = older[next_heading.start() :] if next_heading else ""

    return f"{intro}{heading}\n\n{notes.strip()}\n\n{older}".rstrip() + "\n"


def commit_message(name: str, version: AppVersion, *, forced: bool) -> str:
    """Return the commit message for publishing a version of an app."""
    if version.is_release:
        message = f":tada: Release of app {name} {version.version}"
    else:
        message = f":arrow_up: Updating app {name} to {version.version}"

    if forced:
        message += " (forced update)"

    return message
