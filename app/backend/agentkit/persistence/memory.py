"""agentkit.persistence.memory — pure in-memory session store.

Module role:
    ``InMemorySessionStore`` — a thread-safe in-process dict implementing the
    generic :class:`agentkit.persistence.protocol.SessionStore` surface. Pure
    stdlib + ``agentkit.contracts`` — zero external dependencies. This is the
    quickstart default (boots with no infra) and the Phase-1 fallback a
    consumer upgrades from when a durable backend becomes reachable.

    Domain behaviour (scenario filtering, demo-template seeding) is **not**
    here — a consumer subclasses this and adds those hooks (GridIQ does so in
    ``hosting/fastapi/session/memory.py``).

Layer rule:
    Imports ``agentkit.contracts`` only. Never imports a consumer package.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from agentkit.contracts.models import (
    AgentThread,
    Message,
    Role,
    SessionBase,
    SessionSummaryBase,
)

logger = logging.getLogger(__name__)


def _compute_counts(threads: dict) -> dict:
    """Aggregate activity counts across a session's agent threads.

    Single pass. System messages (prompts) are excluded from every count.
    Pure function — mirrors the consumer-side metadata helper so the generic
    store needs no consumer import.
    """
    message_count = 0
    user_count = 0
    assistant_count = 0
    tool_call_count = 0
    for thread in threads.values():
        msgs = thread.messages if hasattr(thread, "messages") else thread.get("messages", [])
        for msg in msgs:
            role = msg.role if hasattr(msg, "role") else msg.get("role", "")
            role_str = role.value if hasattr(role, "value") else str(role)
            if role_str == "system":
                continue
            message_count += 1
            if role_str == "user":
                user_count += 1
            elif role_str == "assistant":
                assistant_count += 1
            tcs = msg.tool_calls if hasattr(msg, "tool_calls") else msg.get("tool_calls", [])
            tool_call_count += len(tcs)
    return {
        "message_count": message_count,
        "user_prompt_count": user_count,
        "agent_response_count": assistant_count,
        "tool_call_count": tool_call_count,
    }


class InMemorySessionStore:
    """Thread-safe in-memory session store (dev / fallback / quickstart).

    Not suitable for production — data is lost on restart and not shared
    across workers. Holds full :class:`SessionBase` (or subclass) objects in a
    dict guarded by an :class:`asyncio.Lock`.

    Args:
        default_agent_id: Thread id used when ``append_message`` /
            ``update_message`` are called without an explicit ``agent_id``.
            Injected by the consumer (no domain default leaks into the kit).
    """

    def __init__(self, *, default_agent_id: str = "") -> None:
        """Initialise the empty session dict and async lock."""
        self._sessions: dict[str, SessionBase] = {}
        self._lock = asyncio.Lock()
        self._default_agent_id = default_agent_id

    async def is_healthy(self, timeout: float = 2.0) -> bool:
        """Always healthy — no external dependency to probe.

        ``timeout`` is accepted only for protocol parity with durable stores.
        """
        return True

    async def close(self) -> None:
        """No-op — no external resources to release."""
        pass

    async def create(self, session: SessionBase) -> SessionBase:
        """Store a session (including its threads/messages) in the dict."""
        async with self._lock:
            self._sessions[session.id] = session
        return session

    async def get(self, session_id: str) -> SessionBase | None:
        """Retrieve a session by id. Returns None if not found."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_all(self, user_id: str = "") -> list[SessionSummaryBase]:
        """List sessions as summaries with computed activity counts.

        When ``user_id`` is non-empty, returns only sessions owned by that
        user; when empty, returns all sessions. Summaries are computed outside
        the lock (read-only, O(total_messages)) so concurrent message appends
        from active streams are not blocked.
        """
        async with self._lock:
            snapshot = [
                s for s in self._sessions.values()
                if not user_id or s.user_id == user_id
            ]
        summaries: list[SessionSummaryBase] = []
        for s in snapshot:
            counts = _compute_counts(s.threads)
            summaries.append(SessionSummaryBase(
                id=s.id,
                title=s.title,
                user_id=s.user_id,
                message_count=counts["message_count"],
                tool_call_count=counts["tool_call_count"],
                user_prompt_count=counts["user_prompt_count"],
                agent_response_count=counts["agent_response_count"],
                created_at=s.created_at,
                updated_at=s.updated_at,
            ))
        return sorted(summaries, key=lambda s: s.updated_at, reverse=True)

    async def update(
        self, session: SessionBase, *, if_match: str | None = None
    ) -> SessionBase:
        """Replace session data and bump the timestamp.

        ``if_match`` is ignored — the in-memory store has no ETag (a durable
        backend enforces optimistic concurrency).
        """
        async with self._lock:
            session.updated_at = datetime.now(timezone.utc)
            self._sessions[session.id] = session
        return session

    async def delete(self, session_id: str) -> bool:
        """Remove a session. Returns True if one was found and removed."""
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    async def append_message(
        self, session_id: str, message: Message, agent_id: str = ""
    ) -> None:
        """Append a message to an agent's thread.

        The thread must already exist. Raises ``KeyError`` if the session or
        thread is missing.
        """
        agent_id = agent_id or self._default_agent_id
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            if agent_id not in session.threads:
                raise KeyError(
                    f"Thread {agent_id!r} not found in session {session_id}. "
                    f"Create the thread before appending."
                )
            session.threads[agent_id].messages.append(message)
            session.updated_at = datetime.now(timezone.utc)

    async def update_message(
        self, session_id: str, message: Message, agent_id: str = ""
    ) -> None:
        """Replace a message (matched by ``message.id``) in an agent's thread.

        When ``agent_id`` is empty, every thread is searched. Raises
        ``KeyError`` if the session is missing.
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            threads_to_search = (
                [session.threads[agent_id]] if agent_id and agent_id in session.threads
                else session.threads.values()
            )
            for thread in threads_to_search:
                for i, m in enumerate(thread.messages):
                    if m.id == message.id:
                        thread.messages[i] = message
                        session.updated_at = datetime.now(timezone.utc)
                        return

    async def get_thread(self, session_id: str, agent_id: str) -> AgentThread | None:
        """Retrieve a single agent's thread from a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return session.threads.get(agent_id)

    async def create_thread(
        self, session_id: str, agent_id: str, agent_name: str, system_prompt: str = ""
    ) -> AgentThread:
        """Create a new agent thread with an optional system prompt as message 0."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            thread = AgentThread(agent_id=agent_id, agent_name=agent_name)
            if system_prompt:
                thread.messages.append(
                    Message(role=Role.SYSTEM, content=system_prompt, agent_name=agent_id)
                )
            session.threads[agent_id] = thread
            session.updated_at = datetime.now(timezone.utc)
            return thread

    async def get_thread_messages(self, session_id: str, thread_id: str) -> list:
        """Return messages belonging to a specific thread (empty if missing)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            thread = session.threads.get(thread_id)
            if thread is None:
                return []
            return list(thread.messages)


__all__ = ["InMemorySessionStore"]
