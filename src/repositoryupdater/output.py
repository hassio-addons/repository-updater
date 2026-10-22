"""
Output module.

The only place that knows how the updater looks on a terminal. Everything
else reports what happened and lets this module decide how to show it.

Messages are Rich markup. Values from the outside, like names or paths, go
through highlight(), emphasis() or plain(), so a [ in them stays a [.
"""

from __future__ import annotations

import os

from rich.console import Console
from rich.markup import escape
from rich.text import Text


def _workflow_command_value(message: str) -> str:
    """Escape a message for a GitHub Actions workflow command."""
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


class Output:
    """Renders the Repository Updater's progress to the terminal.

    On GitHub Actions, every section becomes a group that folds away in the
    log, and errors become annotations on the run.
    """

    def __init__(self, console: Console | None = None) -> None:
        """Initialize, writing to the given console or to standard output."""
        # Emoji shortcodes stay as they are: commit messages use them. Long
        # lines are not wrapped, so a log keeps one line per message.
        self.console = console or Console(emoji=False, highlight=False, soft_wrap=True)
        self._group_open = False

    @property
    def github_actions(self) -> bool:
        """Return whether this runs on GitHub Actions."""
        return os.environ.get("GITHUB_ACTIONS") == "true"

    def _workflow_command(self, command: str, value: str) -> None:
        """Print a GitHub Actions workflow command."""
        self.console.print(
            f"::{command}::{_workflow_command_value(value)}",
            markup=False,
            soft_wrap=True,
        )

    def title(self, message: str) -> None:
        """Announce the program itself."""
        self.console.print(f"[bold blue]{message}[/]")
        self.console.rule(style="bold blue")

    def section(self, message: str) -> None:
        """Open a new block of work, separated from what came before."""
        self.end_section()
        if self.github_actions:
            # A group title is plain text; render the markup away first.
            self._workflow_command("group", Text.from_markup(message).plain)
            self._group_open = True
            return

        self.console.rule(style="bold cyan")
        self.console.print(f"[cyan]{message}[/]")

    def end_section(self) -> None:
        """Close the block of work that is open, if any."""
        if self._group_open:
            self._workflow_command("endgroup", "")
            self._group_open = False

    def divider(self) -> None:
        """Separate two blocks of work."""
        self.end_section()
        self.console.rule(style="bold green")

    def info(self, message: str) -> None:
        """Report something that needs no attention."""
        self.console.print(message)

    def step(self, message: str) -> None:
        """Announce work about to start, leaving the line open for a result."""
        self.console.print(f"{message}...", end="")

    def done(self, message: str = "Done") -> None:
        """Close an open step that succeeded."""
        self.console.print(f"[green]{message}[/]")

    def skipped(self, message: str = "Skipping") -> None:
        """Close an open step that had nothing to do."""
        self.console.print(f"[blue]{message}[/]")

    def failed(self, message: str = "Failed!") -> None:
        """Close an open step that could not finish."""
        self.console.print(f"[red]{message}[/]")

    def warning(self, message: str) -> None:
        """Report something worth noticing."""
        self.console.print(f"[yellow]{message}[/]")

    def success(self, message: str) -> None:
        """Report a positive outcome."""
        self.console.print(f"[green]{message}[/]")

    def error(self, message: str) -> None:
        """Report what stopped the run."""
        self.end_section()
        if self.github_actions:
            self._workflow_command("error", message)
            return

        self.console.print(f"[bold red]Error:[/] {escape(message)}")

    @staticmethod
    def plain(value: object) -> str:
        """Return a value to use as is inside a message."""
        return escape(str(value))

    @staticmethod
    def highlight(value: object) -> str:
        """Return a value styled for use inside a message."""
        return f"[magenta]{escape(str(value))}[/]"

    @staticmethod
    def emphasis(value: object) -> str:
        """Return a value styled to stand out inside a message."""
        return f"[bold yellow]{escape(str(value))}[/]"
