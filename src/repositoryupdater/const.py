"""Constants used by the Repository Updater program."""

# App configuration files, in the order they are looked up.
CONFIG_FILENAMES = ("config.json", "config.yaml", "config.yml")

# Repository app list files, in the order they are looked up.
APP_LIST_FILENAMES = (".apps.yml", ".addons.yml", ".hassio-addons.yml")

# Architectures assumed when an app does not declare its own.
DEFAULT_ARCHS = ("aarch64", "amd64", "armhf", "armv7", "i386")

# Files copied from an app's own repository into the apps repository; a
# directory is copied whole.
STATIC_FILES = (
    "logo.png",
    "icon.png",
    "README.md",
    "DOCS.md",
    "apparmor.txt",
)
STATIC_DIRECTORIES = ("translations",)

# The template a README is rendered from, in both kinds of repository.
README_TEMPLATE = ".README.j2"
