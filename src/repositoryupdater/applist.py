"""The app list an apps repository declares in its .apps.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import yaml
from mashumaro import DataClassDictMixin, field_options

from .exceptions import InvalidAppListError, InvalidChannelError

# What every app in the list has to say about itself.
REQUIRED_APP_KEYS = ("image", "repository", "target")


class Channel(StrEnum):
    """How stable the versions an apps repository publishes are."""

    STABLE = "stable"
    BETA = "beta"
    EDGE = "edge"


class ChangelogMode(StrEnum):
    """What a release does to the CHANGELOG.md of an app."""

    # The changelog holds the notes of the newest release only.
    REPLACE = "replace"
    # Every release adds its notes on top, under a heading of its version.
    PREPEND = "prepend"


@dataclass(frozen=True, kw_only=True)
class AppEntry(DataClassDictMixin):
    """One app in the list: where it lives, and where it goes."""

    # Directory holding this app inside the apps repository.
    repository_target: str
    image: str
    # The "owner/name" that holds the app's own source.
    repository: str
    # Directory holding this app inside its own repository.
    app_target: str = field(metadata=field_options(alias="target"))


@dataclass(frozen=True, kw_only=True)
class AppList(DataClassDictMixin):
    """Everything an apps repository declares about itself."""

    channel: Channel
    apps: list[AppEntry]
    changelog: ChangelogMode = ChangelogMode.REPLACE

    @classmethod
    def __pre_deserialize__(cls, d: dict[Any, Any]) -> dict[Any, Any]:
        """Turn the apps mapping into entries that know their own directory.

        Older app lists call the mapping "addons"; both keep working.
        """
        apps = d.get("apps", d.get("addons")) or {}
        return {
            **d,
            "apps": [
                {**app, "repository_target": target} for target, app in apps.items()
            ],
        }


def parse_app_list(filename: str, content: bytes) -> AppList:
    """Parse a repository app list, rejecting anything we cannot work with."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exception:
        raise InvalidAppListError(filename, "it is not valid YAML") from exception

    if not isinstance(data, dict):
        raise InvalidAppListError(filename, "it does not contain a mapping")

    if "channel" not in data:
        raise InvalidAppListError(filename, 'it does not declare a "channel"')

    if data["channel"] not in set(Channel):
        raise InvalidChannelError(str(data["channel"]))

    if data.get("changelog", ChangelogMode.REPLACE) not in set(ChangelogMode):
        modes = ", ".join(ChangelogMode)
        msg = f'"changelog" must be one of {modes}'
        raise InvalidAppListError(filename, msg)

    _check_apps(filename, data.get("apps", data.get("addons")))
    return AppList.from_dict(data)


def _check_apps(filename: str, apps: object) -> None:
    """Reject apps the app list does not describe completely."""
    if apps is None:
        return

    if not isinstance(apps, dict):
        raise InvalidAppListError(filename, "its apps are not a mapping")

    for target, app in apps.items():
        if not isinstance(app, dict):
            msg = f'app "{target}" is not a mapping'
            raise InvalidAppListError(filename, msg)

        for key in REQUIRED_APP_KEYS:
            if key not in app:
                msg = f'app "{target}" is missing "{key}"'
                raise InvalidAppListError(filename, msg)
