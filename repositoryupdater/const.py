"""Constants used by the Repository Updater program."""

CHANNEL_STABLE = "stable"
CHANNEL_BETA = "beta"
CHANNEL_EDGE = "edge"
CHANNELS = [CHANNEL_STABLE, CHANNEL_BETA, CHANNEL_EDGE]

# How a release updates the app's CHANGELOG.md in the apps repository.
CHANGELOG_REPLACE = "replace"
CHANGELOG_PREPEND = "prepend"
CHANGELOG_MODES = [CHANGELOG_REPLACE, CHANGELOG_PREPEND]

# App configuration files, in the order they are looked up.
CONFIG_FILENAMES = ("config.json", "config.yaml", "config.yml")

# Repository app list files, in the order they are looked up.
APP_LIST_FILENAMES = (".apps.yml", ".addons.yml", ".hassio-addons.yml")

# Architectures assumed when an app does not declare its own.
DEFAULT_ARCHS = ("aarch64", "amd64", "armhf", "armv7", "i386")
