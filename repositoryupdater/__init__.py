"""
Community Home Assistant Add-ons Repository Updater.

Reads remote add-on repositories, determines versions and generates
changelogs to update the add-on repository fully automated.

Mainly used by the Community Home Assistant Add-ons project.

Please note, this program cannot be used with the general documented
Home Assistant add-on repository approach.
"""

APP_NAME = "repository-updater"
APP_FULL_NAME = "Community Home Assistant Add-ons Repository Updater"
APP_VERSION = "0.6.0"
APP_DESCRIPTION = __doc__

__author__ = "Franck Nijhof"
__email__ = "frenck@addons.community"
__copyright__ = "Copyright 2018-2021, Franck Nijhof"
__license__ = "MIT"
__url__ = "https://github.com/hassio-addons/repository-updater"
__download__ = (
    "https://github.com/hassio-addons/repository-updater/archive/0.6.0.tar.gz"
)
__version__ = APP_VERSION
