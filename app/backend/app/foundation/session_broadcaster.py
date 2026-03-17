"""Per-session SSE event broadcaster for delegation streaming.

Module role:
    Provides ``SessionBroadcaster`` — a per-session fan-out that pushes
    StreamEvent objects tagged with ``agent_id`` to SSE subscribers.
    When the delegation tool runs a specialist agent with ``stream=True``,
    each SDK update is mapped to a StreamEvent and broadcast here. The
    frontend subscribes via ``GET /api/sessions/{id}/events`` and routes
    events to the correct agent chat slice.

    Follows the same pattern as ``LogBroadcaster`` — thread-safe broadcast,
    async subscribe generator, per-subscriber queue with automatic cleanup.

Key collaborators:
    - tools/delegation/__init__.py — calls broadcast() during specialist streaming
    - app/routers/sessions.py     — SSE endpoint calls subscribe()
    - Frontend useSessionEvents   — EventSource consumer

Dependents:
    Called by: delegation tool (broadcast), sessions router (subscribe)
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class SessionBroadcaster:
    """Per-session SSE event fan-out for delegation streaming.

    Each active session gets its own broadcaster. Events are tagged with
    ``agent_id`` so the frontend can route them to the correct chat slice.

    Thread-safe — broadcast() may be called from async tool execution
    contexts while subscribe() runs in a different async task.
    """

    def __init__(self, session_id: str, max_queue: int = 200):
        """Initialize the broadcaster.

        Args:
            session_id: The session this broadcaster serves.
            max_queue: Max per-subscriber queue depth before pruning.
        """
        self.session_id = session_id
        self._lock = threading.Lock()
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}
        self._max_queue = max_queue

    def broadcast(self, agent_id: str, event_type: str, data: dict[str, Any]) -> None:
        """Push a delegation event to all subscribers.

        Args:
            agent_id: The agent this event belongs to (e.g. "networkInvestigator").
            event_type: The StreamEventType value (e.g. "token", "tool_call_start").
            data: The event payload dict.
        """
        record = {
            "agent_id": agent_id,
            "event": event_type,
            "data": data,
        }

        with self._lock:
            snapshot = list(self._subscribers.items())

        # Distribute outside the lock
        dead: list[asyncio.Queue] = []
        for q, loop in snapshot:
            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, record)
                else:
                    q.put_nowait(record)
            except (asyncio.QueueFull, RuntimeError):
                dead.append(q)

        if dead:
            with self._lock:
                for q in dead:
                    self._subscribers.pop(q, None)

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        """Async generator yielding SSE-formatted delegation events.

        Yields dicts that sse-starlette formats as named SSE events:
        ``event: delegation\\ndata: {json}\\n\\n``

        Yields:
            Dict with 'event' and 'data' keys for sse-starlette.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)

        with self._lock:
            self._subscribers[q] = loop
        try:
            while True:
                record = await q.get()
                # sse-starlette expects {"event": str, "data": str}
                yield {
                    "event": "delegation",
                    "data": json.dumps(record),
                }
        finally:
            with self._lock:
                self._subscribers.pop(q, None)

    @property
    def subscriber_count(self) -> int:
        """Number of active SSE subscribers."""
        with self._lock:
            return len(self._subscribers)


# ── Module-level registry of active broadcasters ─────────────────────────────

_broadcasters: dict[str, SessionBroadcaster] = {}
_registry_lock = threading.Lock()


def get_session_broadcaster(session_id: str) -> SessionBroadcaster:
    """Get or create a broadcaster for a session.

    Args:
        session_id: The session identifier.

    Returns:
        The SessionBroadcaster for this session (created on first access).
    """
    if session_id in _broadcasters:
        return _broadcasters[session_id]

    with _registry_lock:
        if session_id not in _broadcasters:
            _broadcasters[session_id] = SessionBroadcaster(session_id)
            logger.debug("Created session broadcaster for %s", session_id)
        return _broadcasters[session_id]


def remove_session_broadcaster(session_id: str) -> None:
    """Remove a session's broadcaster. Called on session delete."""
    with _registry_lock:
        _broadcasters.pop(session_id, None)
