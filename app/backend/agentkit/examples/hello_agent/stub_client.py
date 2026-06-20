"""EchoClientFactory — a stub ``AgentClient`` for the headless quickstart.

Satisfies the ``agentkit.core.AgentClient`` seam (an ``as_agent(...)`` factory)
without any SDK or network. The built ``EchoAgent`` streams the user's message
back token-by-token as SDK-shaped update objects (``author_name`` / ``text`` /
``contents``) that the domain-blind ``map_update_to_events`` mapper consumes.

This is the legitimate way to prove the wiring in a few lines with no DNS — a
real deployment passes a MAF adapter instead (the ``[maf]`` extra) and changes
nothing else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Update:
    """Minimal SDK-shaped streaming update (duck-typed by the mapper)."""

    text: str = ""
    author_name: str = "HelloAgent"
    contents: list[Any] = field(default_factory=list)


class EchoAgent:
    """A built agent that streams its input back as tokens."""

    def __init__(self, name: str) -> None:
        self._name = name

    async def run(self, message: str, *, stream: bool = True) -> AsyncIterator[_Update]:
        """Yield the echoed message as a short stream of token updates."""
        reply = f"echo: {message}"
        for word in reply.split(" "):
            yield _Update(text=word + " ", author_name=self._name)


class EchoClientFactory:
    """Stub ``AgentClient`` — its ``as_agent`` returns an :class:`EchoAgent`."""

    def as_agent(self, *, name: str = "HelloAgent", **_: Any) -> EchoAgent:
        """Build an echo agent (ignores tools/middleware/providers — it's a stub)."""
        return EchoAgent(name)

    def close(self) -> None:
        """No resources to release."""
