"""Common fixtures and helpers for the Repository Updater tests."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    """Return a recorded fixture, by its path below tests/fixtures."""
    return (FIXTURES / name).read_bytes()
