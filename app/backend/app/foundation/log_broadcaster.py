"""Reusable SSE log broadcast infrastructure.

Module role:
    Provides ``LogBroadcaster`` — a thread-safe fan-out class that pushes log
    records to multiple SSE subscriber queues.  Integrates with Python's
    ``logging`` module via a custom ``Handler`` returned by ``get_handler()``.

    Two module-level singletons are provided:
      - ``get_agent_broadcaster()`` — captures agent SDK + tool log events
      - ``get_backend_broadcaster()`` — captures backend framework / HTTP logs

    Ported from ``azure-autonomous-network-demo/graph-query-api/log_broadcaster.py``
    with module-level singletons added (lazy-init pattern matching
    ``FabricThrottleGate`` in ``tools/fabric/_throttle.py``).

Architecture:
    LogBroadcaster
      ├── broadcast(record)     — push a dict to every subscriber queue
      ├── subscribe()           — async generator yielding SSE-formatted events
      └── get_handler(level)    — return a logging.Handler that calls broadcast()

    _BroadcastHandler (internal)
      └── emit(LogRecord)       — serialise log record → dict → broadcast()

Key collaborators:
    - ``app/routers/observability.py`` — SSE endpoints consume ``subscribe()``
    - ``app/main.py``                — wires handlers to loggers at startup

Dependents:
    Called by: ``routers/observability.py`` (subscribe), ``main.py`` (get_handler)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections import deque
from datetime import datetime, timezone
from typing import AsyncGenerator

# ── Sensitive data patterns to strip before broadcasting ─────────────────────

# Matches Authorization header values and common token/key patterns
_SENSITIVE_RE = re.compile(
    r"(Bearer\s+\S+|Authorization:\s*\S+|api[_-]?key[=:]\s*\S+)",
    re.IGNORECASE,
)


class LogBroadcaster:
    """Fan-out log records to multiple SSE subscriber queues (thread-safe).

    Maintains a circular replay buffer so new subscribers receive recent
    history on connect.  Each subscriber gets its own ``asyncio.Queue``;
    dead subscribers (full queues, closed loops) are pruned automatically.

    Purpose:
        Central log distribution hub for the observability panel.

    Side effects:
        None — read-only observer of the logging system.

    Dependencies:
        Pure stdlib (asyncio, threading, json, logging).
    """

    def __init__(self, max_buffer: int = 100, max_queue: int = 500):
        """Initialise broadcaster.

        Parameters:
            max_buffer: Maximum number of log entries to retain in the replay
                        buffer.  New subscribers receive these on connect.
            max_queue:  Maximum per-subscriber queue depth.  If a subscriber
                        falls behind, it is disconnected (queue full → pruned).

        Raises:
            Nothing.
        """
        # Thread lock — broadcast() may be called from non-async logging threads
        self._lock = threading.Lock()
        # Subscriber map: asyncio.Queue → event loop that owns it
        self._subscribers: dict[asyncio.Queue, asyncio.AbstractEventLoop] = {}
        # Circular replay buffer for new subscriber catch-up
        self._buffer: deque[dict] = deque(maxlen=max_buffer)
        # Per-subscriber queue depth limit
        self._max_queue = max_queue
        # Grace period counter — subscribers get 3 strikes before pruning
        self._skip_counts: dict[asyncio.Queue, int] = {}

    def broadcast(self, record: dict) -> None:
        """Push a log record dict to every subscriber (thread-safe).

        Serialises the record once before distribution — avoids redundant
        json.dumps() per subscriber in subscribe().

        Parameters:
            record: Serialised log entry dict with keys: ts, level, name, msg.

        Side effects:
            Appends to replay buffer; enqueues to all subscriber queues.
            Prunes dead subscribers (full queue or stopped event loop).
        """
        # Pre-serialise once — all subscribers receive the same string
        serialised = json.dumps(record)

        with self._lock:
            self._buffer.append(serialised)
            snapshot = list(self._subscribers.items())

        # Distribute outside the lock to avoid blocking other threads
        dead: list[asyncio.Queue] = []
        for q, loop in snapshot:
            try:
                if loop is not None and loop.is_running():
                    # Cross-thread enqueue via the subscriber's event loop
                    loop.call_soon_threadsafe(q.put_nowait, serialised)
                else:
                    q.put_nowait(serialised)
                # Successful delivery — reset skip counter
                self._skip_counts.pop(q, None)
            except (asyncio.QueueFull, RuntimeError):
                # Grace period — allow 3 consecutive failures before pruning
                count = self._skip_counts.get(q, 0) + 1
                self._skip_counts[q] = count
                if count >= 3:
                    dead.append(q)

        # Remove unreachable subscribers
        if dead:
            with self._lock:
                for q in dead:
                    self._subscribers.pop(q, None)
                    self._skip_counts.pop(q, None)

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE-formatted log events.

        On connect, replays the buffer contents then streams live events.
        Automatically unregisters on generator close (client disconnect).

        Yields:
            SSE-formatted strings: ``event: log\\ndata: {json}\\n\\n``
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)

        # Register subscriber and snapshot current buffer under lock
        with self._lock:
            buffered = list(self._buffer)
            self._subscribers[q] = loop
        try:
            # Replay buffered history (pre-serialised strings)
            for rec in buffered:
                yield f"event: log\ndata: {rec}\n\n"
            # Stream live events (pre-serialised strings)
            while True:
                rec = await q.get()
                yield f"event: log\ndata: {rec}\n\n"
        finally:
            # Unregister on disconnect
            with self._lock:
                self._subscribers.pop(q, None)

    def get_handler(self, level: int = logging.INFO) -> logging.Handler:
        """Return a ``logging.Handler`` that broadcasts to this instance.

        Parameters:
            level: Minimum log level for the handler (default: INFO).

        Returns:
            A ``_BroadcastHandler`` configured with the given level.
        """
        handler = _BroadcastHandler(self)
        handler.setLevel(level)
        return handler


class _BroadcastHandler(logging.Handler):
    """Logging handler that serialises records and broadcasts them.

    Strips sensitive data (auth headers, API keys) from log messages
    before broadcasting to prevent credential leakage to the frontend.

    Purpose:
        Bridge between Python's logging system and LogBroadcaster.

    Dependencies:
        LogBroadcaster instance (passed at construction).
    """

    def __init__(self, broadcaster: LogBroadcaster):
        """Initialise handler.

        Parameters:
            broadcaster: The LogBroadcaster instance to push records to.
        """
        super().__init__()
        self._broadcaster = broadcaster

    def emit(self, record: logging.LogRecord) -> None:
        """Serialise a LogRecord and broadcast it.

        Parameters:
            record: Standard Python LogRecord from the logging framework.

        Side effects:
            Calls broadcaster.broadcast() with the serialised dict.
        """
        try:
            # Format the message (applies any Formatter attached to handler)
            msg = self.format(record)
            # Strip sensitive data before broadcasting to the frontend
            msg = _SENSITIVE_RE.sub("[REDACTED]", msg)

            entry = {
                "ts": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).strftime("%H:%M:%S.%f")[:-3],
                "level": record.levelname,
                "name": record.name,
                "msg": msg,
            }
            self._broadcaster.broadcast(entry)
        except Exception:
            self.handleError(record)


# ── Module-level singletons (lazy-init, thread-safe) ───────────────────────

_agent_broadcaster: LogBroadcaster | None = None
_backend_broadcaster: LogBroadcaster | None = None
_frontend_broadcaster: LogBroadcaster | None = None
_broadcaster_lock = threading.Lock()


def get_agent_broadcaster() -> LogBroadcaster:
    """Return the singleton LogBroadcaster for agent/tool log events."""
    global _agent_broadcaster
    if _agent_broadcaster is None:
        with _broadcaster_lock:
            if _agent_broadcaster is None:
                _agent_broadcaster = LogBroadcaster(max_buffer=100)
    return _agent_broadcaster


def get_backend_broadcaster() -> LogBroadcaster:
    """Return the singleton LogBroadcaster for backend framework log events."""
    global _backend_broadcaster
    if _backend_broadcaster is None:
        with _broadcaster_lock:
            if _backend_broadcaster is None:
                _backend_broadcaster = LogBroadcaster(max_buffer=100)
    return _backend_broadcaster


def get_frontend_broadcaster() -> LogBroadcaster:
    """Return the singleton LogBroadcaster for frontend console log events."""
    global _frontend_broadcaster
    if _frontend_broadcaster is None:
        with _broadcaster_lock:
            if _frontend_broadcaster is None:
                _frontend_broadcaster = LogBroadcaster(max_buffer=100)
    return _frontend_broadcaster
