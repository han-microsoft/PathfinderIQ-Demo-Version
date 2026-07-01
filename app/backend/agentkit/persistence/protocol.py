"""agentkit.persistence.protocol — generic session-store interface.

Module role:
    Defines the domain-blind ``SessionStore`` protocol: the CRUD + per-agent
    thread + lifecycle (``is_healthy`` / ``close``) surface every session
    backend must implement. Consumers depend on this protocol, not a concrete
    backend (dependency inversion).

    Domain hooks (scenario filtering, demo-template seeding) are intentionally
    **absent** here — they live on the consumer's extended protocol so the
    generic surface stays reusable. The injectable two-phase-upgrade surface
    (``is_healthy`` + ``close``) is present so a consumer can boot an in-memory
    store and swap to a durable one when reachable.

Layer rule:
    Imports ``agentkit.contracts`` only. Never imports a consumer package.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agentkit.contracts.models import (
    AgentThread,
    Message,
    SessionBase,
    SessionSummaryBase,
)


@runtime_checkable
class SessionStore(Protocol):
    """Generic interface for session persistence.

    All methods are async (the lifecycle ``set``-style hooks excepted). Backends
    handle their own concurrency (an async lock for in-memory, SDK-level for a
    durable store).

    Methods:
        create          — persist a new session
        get             — retrieve a session by id (with threads/messages)
        list_all        — list sessions as summaries
        update          — replace session metadata
        delete          — remove a session
        append_message  — add a message to an existing thread
        update_message  — replace a message (finalize streaming content)
        get_thread / create_thread / get_thread_messages — per-agent threads
        is_healthy      — bounded reachability probe (two-phase-upgrade surface)
        close           — release backend resources

    Typed against the generic :class:`SessionBase` / :class:`SessionSummaryBase`
    so a domain consumer's ``Session`` subclass satisfies it structurally.
    """

    async def create(self, session: SessionBase) -> SessionBase: ...
    async def get(self, session_id: str) -> SessionBase | None: ...
    async def list_all(self, user_id: str = "") -> list[SessionSummaryBase]: ...
    async def update(
        self, session: SessionBase, *, if_match: str | None = None
    ) -> SessionBase: ...
    async def delete(self, session_id: str) -> bool: ...
    async def append_message(
        self, session_id: str, message: Message, agent_id: str = ""
    ) -> None: ...
    async def update_message(
        self, session_id: str, message: Message, agent_id: str = ""
    ) -> None: ...

    # ── Per-agent threads ──
    async def get_thread(self, session_id: str, agent_id: str) -> AgentThread | None: ...
    async def create_thread(
        self, session_id: str, agent_id: str, agent_name: str, system_prompt: str = ""
    ) -> AgentThread: ...
    async def get_thread_messages(
        self, session_id: str, thread_id: str
    ) -> list[Message]: ...

    # ── Lifecycle / two-phase upgrade surface ──
    async def is_healthy(self, timeout: float = 2.0) -> bool: ...
    async def close(self) -> None: ...


__all__ = ["SessionStore"]
