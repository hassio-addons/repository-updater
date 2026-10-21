"""
Home Assistant Community Apps Repository Updater.

Reads remote app repositories, determines versions and generates
changelogs to update the app repository fully automated.

Mainly used by the Home Assistant Community Apps project.

Please note, this program cannot be used with the general documented
Home Assistant app repository approach.
"""

from importlib.metadata import version

APP_FULL_NAME = "Home Assistant Community Apps Repository Updater"
APP_VERSION = version("repository-updater")

__version__ = APP_VERSION
