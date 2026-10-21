"""
Output module.

The only place that knows how the updater looks on a terminal. Everything
else reports what happened and lets this module decide how to show it.
"""

from __future__ import annotations

import click


class Output:
    """Renders the Repository Updater's progress to the terminal."""

    def title(self, message: str) -> None:
        """Announce the program itself."""
        click.secho(message, fg="blue", bold=True)
        click.secho("-" * 51, fg="blue", bold=True)

    def section(self, message: str) -> None:
        """Open a new block of work, separated from what came before."""
        click.secho("-" * 50, fg="cyan", bold=True)
        click.secho(message, fg="cyan")

    def divider(self) -> None:
        """Separate two blocks of work."""
        click.secho("-" * 50, fg="green", bold=True)

    def info(self, message: str) -> None:
        """Report something that needs no attention."""
        click.echo(message)

    def step(self, message: str) -> None:
        """Announce work about to start, leaving the line open for a result."""
        click.echo(f"{message}...", nl=False)

    def done(self, message: str = "Done") -> None:
        """Close an open step that succeeded."""
        click.secho(message, fg="green")

    def skipped(self, message: str = "Skipping") -> None:
        """Close an open step that had nothing to do."""
        click.secho(message, fg="blue")

    def failed(self, message: str = "Failed!") -> None:
        """Close an open step that could not finish."""
        click.secho(message, fg="red")

    def warning(self, message: str) -> None:
        """Report something worth noticing."""
        click.secho(message, fg="yellow")

    def success(self, message: str) -> None:
        """Report a positive outcome."""
        click.secho(message, fg="green")

    def highlight(self, value: str) -> str:
        """Return a value styled for use inside a message."""
        return click.style(value, fg="magenta")

    def emphasis(self, value: str) -> str:
        """Return a value styled to stand out inside a message."""
        return click.style(value, fg="yellow", bold=True)
