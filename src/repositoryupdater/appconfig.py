"""Reading and writing the configuration file of an app."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import yaml
from mashumaro.mixins.orjson import DataClassORJSONMixin

from .const import DEFAULT_ARCHS
from .exceptions import InvalidAppConfigError

# What every app configuration has to say about the app.
REQUIRED_KEYS = ("name", "slug", "description")

# What YAML 1.2, the version the Supervisor reads, takes for something other
# than a string: integers, floats, booleans and null, from its core schema.
# PyYAML writes YAML 1.1, where "58899e0" is a string it leaves unquoted, but
# the Supervisor reads that short commit SHA as the number 58899.0.
YAML_12_NOT_A_STRING = re.compile(
    r"""
    [-+]?[0-9]+                                   # integer
    | 0o[0-7]+ | 0x[0-9a-fA-F]+                   # octal, hexadecimal
    | [-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?  # float
    | [-+]?\.(inf|Inf|INF) | \.(nan|NaN|NAN)       # infinity, not a number
    | true|True|TRUE|false|False|FALSE            # boolean
    | null|Null|NULL|~                            # null
    """,
    re.VERBOSE,
)


class _QuotedString(str):
    """A string that has to stay a string, whoever reads the YAML."""

    __slots__ = ()


class _Dumper(yaml.SafeDumper):
    """Writes YAML that YAML 1.1 and 1.2 parsers read the same way."""


_Dumper.add_representer(
    _QuotedString,
    lambda dumper, value: dumper.represent_scalar(
        "tag:yaml.org,2002:str", str(value), style="'"
    ),
)


@dataclass(frozen=True, kw_only=True)
class AppDetails(DataClassORJSONMixin):
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

    if YAML_12_NOT_A_STRING.fullmatch(version):
        published["version"] = _QuotedString(version)

    return yaml.dump(
        published, Dumper=_Dumper, default_flow_style=False, sort_keys=False
    )
