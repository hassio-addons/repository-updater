"""The READMEs, changelogs and commit messages an update writes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import emoji
from jinja2 import BaseLoader, Environment

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .appconfig import AppDetails
    from .applist import AppEntry, Channel
    from .github import Commit, Release, Repository
    from .versions import AppVersion

README_COMMIT_MESSAGE = ":books: Updated README"


def render_template(template: str, data: Mapping[str, Any]) -> str:
    """Render a README template."""
    # Autoescaping is off on purpose: these templates render Markdown.
    environment = Environment(  # noqa: S701
        loader=BaseLoader(),
        trim_blocks=True,
        extensions=["jinja2.ext.loopcontrols"],
    )
    return environment.from_string(template).render(**data)


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
        "date": version.release.created_at if version.release else version.commit.date,
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


def commit_message(name: str, version: AppVersion, *, forced: bool) -> str:
    """Return the commit message for publishing a version of an app."""
    if version.is_release:
        message = f":tada: Release of app {name} {version.version}"
    else:
        message = f":arrow_up: Updating app {name} to {version.version}"

    if forced:
        message += " (forced update)"

    return message
