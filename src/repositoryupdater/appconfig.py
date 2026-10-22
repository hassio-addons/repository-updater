"""Reading and writing the configuration file of an app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import yaml

from .const import DEFAULT_ARCHS
from .exceptions import InvalidAppConfigError

# What every app configuration has to say about the app.
REQUIRED_KEYS = ("name", "slug", "description")


@dataclass(frozen=True, kw_only=True)
class AppDetails:
    """What the READMEs show about an app, from its configuration."""

    name: str
    slug: str
    description: str
    url: str | None
    archs: tuple[str, ...]

    @classmethod
    def from_config(cls, location: str, config: dict[str, Any]) -> AppDetails:
        """Pick the details out of an app configuration."""
        for key in REQUIRED_KEYS:
            if key not in config:
                raise InvalidAppConfigError(location, f'it is missing "{key}"')

        return cls(
            name=config["name"],
            slug=config["slug"],
            description=config["description"],
            url=config.get("url"),
            archs=tuple(config.get("arch", DEFAULT_ARCHS)),
        )


def parse_config(location: str, content: bytes) -> dict[str, Any]:
    """Parse an app configuration, in JSON or YAML depending on its name."""
    try:
        if location.endswith(".json"):
            config = json.loads(content)
        else:
            config = yaml.safe_load(content)
    except (ValueError, yaml.YAMLError) as exception:
        msg = "it is not valid JSON or YAML"
        raise InvalidAppConfigError(location, msg) from exception

    if not isinstance(config, dict):
        raise InvalidAppConfigError(location, "it does not contain a mapping")

    return config


def render_config(
    filename: str, config: dict[str, Any], *, version: str, image: str
) -> str:
    """Return the configuration an apps repository publishes for an app.

    The source configuration, stamped with the version being published and
    the image to pull, in the same format it came in.
    """
    published = {**config, "version": version, "image": image}

    if filename.endswith(".json"):
        return json.dumps(
            published, ensure_ascii=False, indent=2, separators=(",", ": ")
        )

    return yaml.dump(published, default_flow_style=False, sort_keys=False)
