"""Repository Updater bootstrap."""

from .cli import repository_updater

if __name__ == "__main__":
    # Click fills in the arguments from the command line.
    repository_updater()  # pylint: disable=missing-kwoa
