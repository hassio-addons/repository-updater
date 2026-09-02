"""Constants used by the Repository Updater program."""

CHANNEL_STABLE = "stable"
CHANNEL_BETA = "beta"
CHANNEL_EDGE = "edge"
CHANNELS = [CHANNEL_STABLE, CHANNEL_BETA, CHANNEL_EDGE]

# App configuration files, in the order they are looked up.
CONFIG_FILENAMES = ("config.json", "config.yaml", "config.yml")
