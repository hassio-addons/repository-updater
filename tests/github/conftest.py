"""Fixtures for the GitHub client tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from aioresponses import aioresponses
from aioresponses import core as aioresponses_core

from repositoryupdater.github import GitHub

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

FIXTURES = Path(__file__).parent.parent / "fixtures" / "github"


def fixture_bytes(name: str) -> bytes:
    """Return a recorded GitHub answer as it came over the wire."""
    return (FIXTURES / name).read_bytes()


class AioresponsesClientResponse(aioresponses_core.ClientResponse):
    """ClientResponse with the stream writer aiohttp 3.14 and later require.

    aioresponses does not hand one over yet. Drop this once it does.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize, handing over a stream writer."""
        kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
        super().__init__(*args, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def aioresponses_compatibility() -> Generator[None]:
    """Patch aioresponses for the aiohttp version in use."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(aioresponses_core, "ClientResponse", AioresponsesClientResponse)
    yield
    monkeypatch.undo()


@pytest.fixture
def responses() -> Generator[aioresponses]:
    """Return a mock of every HTTP request made."""
    with aioresponses() as mocker:
        yield mocker


@pytest.fixture
async def github() -> AsyncGenerator[GitHub]:
    """Return a GitHub client with its own session."""
    async with GitHub("the-token") as client:
        yield client
