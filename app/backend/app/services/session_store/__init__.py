"""Session storage protocol — interface for session persistence backends.

Module role:
    Defines the ``SessionStore`` protocol (interface) used by route handlers
    and dependency injection. Concrete implementations live in separate modules:
      - ``session_store/memory.py``  — InMemorySessionStore (dev / fallback)
      - ``session_store/cosmos.py``  — CosmosSessionStore (production, Phase 1)

    Also defines ``SessionStoreUnavailable`` — the exception raised when the
    Cosmos circuit breaker is open. Routers catch this to degrade gracefully
    instead of returning 500s.

    Uses the Protocol pattern for dependency inversion — consumers depend on
    the protocol, not a concrete implementation.

Key collaborators:
    - ``app.models.Session``, ``Message``, ``SessionSummary`` — stored objects
    - ``main.py``  — selects and instantiates the store at startup
    - ``deps.py``  — injects the store into route handlers

Dependents:
    Called by: ``router_sessions.py`` (CRUD), ``router_chat.py`` (message append/update)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.foundation.models import AgentThread, Message, Session, SessionSummary
from typing import TYPE_CHECKING


class SessionStoreUnavailable(Exception):
    """Raised when the session store circuit breaker is open.

    Callers should catch this and degrade gracefully — e.g., emit an SSE
    error event rather than returning a 500. The chat stream can continue
    without persistence (messages are lost but the user sees the response).

    Defined here (in the protocol module) rather than in the Cosmos
    implementation so routers can import it without coupling to a
    concrete backend.
    """
    pass


@runtime_checkable
class SessionStore(Protocol):
    """Interface for session persistence.

    All methods are async. Implementations must handle their own
    concurrency (locks for in-memory, SDK-level for Cosmos).

    Methods:
        create          — persist a new session
        get             — retrieve session by ID (with messages)
        list_all        — list all sessions as summaries
        update          — update session metadata (title, etc.)
        delete          — remove session and its messages
        append_message  — add a message to an existing session
        update_message  — replace a message (finalize streaming content)
    """

    async def create(self, session: Session) -> Session: ...
    async def get(self, session_id: str) -> Session | None: ...
    async def list_all(self, user_id: str = "") -> list[SessionSummary]: ...
    async def update(self, session: Session) -> Session: ...
    async def delete(self, session_id: str) -> bool: ...
    async def append_message(self, session_id: str, message: Message, agent_id: str = "") -> None: ...
    async def update_message(self, session_id: str, message: Message, agent_id: str = "") -> None: ...

    # ── v3 thread methods ──
    async def get_thread(self, session_id: str, agent_id: str) -> AgentThread | None: ...
    async def create_thread(
        self, session_id: str, agent_id: str, agent_name: str, system_prompt: str = ""
    ) -> AgentThread: ...

    async def get_thread_messages(self, session_id: str, thread_id: str) -> list[Message]: ...

