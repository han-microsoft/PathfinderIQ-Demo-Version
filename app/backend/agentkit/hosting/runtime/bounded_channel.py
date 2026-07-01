"""Bounded SSE event channel with visible overflow markers.

Module role:
    A single canonical implementation of the bounded-queue +
    rate-limited overflow-marker pattern. Any consumer that fans
    stream events into an ``asyncio.Queue`` shared with a slow SSE
    subscriber needs the same contract: ``put_nowait``, log on
    overflow, drop the event, and emit at most one categorical marker
    per ``(session_id, agent_id)`` per ``marker_interval_seconds``
    carrying the drop count since the last marker.

    Keeping one channel object pins the contract in one file so
    independent call sites (e.g. a per-request delegation queue and an
    app-scoped fan-out broker) cannot drift apart.

Contract preserved exactly:
    - Drop is logged via the supplied ``logger`` (caller picks the channel name).
    - Marker enqueue is itself ``put_nowait`` \u2014 if even the marker cannot
      fit, the drop is logged but the loop is not retried. Looping on a
      permanently-full queue would amplify the overflow, not surface it.
    - Marker rate-limit is keyed by ``(session_id, agent_id)`` so a single
      slow subscriber does not silence markers for other (session, agent)
      pairs sharing the same channel instance.
    - Drop counter surfaces in the marker payload as ``"dropped": N`` so the
      UI can render "N frames lost".

Layer note:
    Imports ``agentkit.contracts.models`` (the event enum) and stdlib
    only. Imports zero consumer packages.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType


# Default rate-limit window. Callers may override per-channel.
DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS: float = 5.0


class BoundedEventChannel:
    """Stateful overflow-marker policy for one logical event channel.

    A single instance owns the rate-limit + drop-counter state for ALL keys
    routed through it. Callers pass the queue explicitly per publish so the
    same channel can serve multiple queues (e.g. one chat request, or a
    fan-out broker). Per-queue rate-limit isolation is achieved by using
    one channel instance per queue (per-request) or one shared instance
    per broker (fan-out).
    """

    def __init__(
        self,
        *,
        marker_event_type: StreamEventType,
        log_event: str,
        logger: logging.Logger,
        marker_interval_seconds: float = DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS,
    ) -> None:
        # ``marker_event_type`` lets each call site pick the categorical
        # marker frame (e.g. a delegation-error vs background-error enum
        # member) without leaking transport-layer enums up into the helper.
        self._marker_event_type = marker_event_type
        self._log_event = log_event
        self._logger = logger
        self._marker_interval = float(marker_interval_seconds)
        # Last-marker timestamps gate the synthetic marker rate. Keyed by
        # the (session_id, agent_id) that overflowed.
        self._last_marker: dict[tuple[str, str], float] = {}
        # Drop counters since the last successful marker emission.
        self._drops: dict[tuple[str, str], int] = defaultdict(int)

    def publish(
        self,
        queue: asyncio.Queue[StreamEvent],
        event: StreamEvent,
        *,
        session_id: str,
        agent_id: str,
        extra_log_fields: dict[str, Any] | None = None,
    ) -> None:
        """Publish ``event`` to ``queue`` or surface overflow."""
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass
        self._handle_overflow(
            queue,
            event,
            session_id=session_id,
            agent_id=agent_id or "",
            extra_log_fields=extra_log_fields or {},
        )

    def _handle_overflow(
        self,
        queue: asyncio.Queue[StreamEvent],
        event: StreamEvent,
        *,
        session_id: str,
        agent_id: str,
        extra_log_fields: dict[str, Any],
    ) -> None:
        key = (session_id, agent_id)
        self._drops[key] += 1
        try:
            dropped_event_type = event.event.value
        except AttributeError:
            dropped_event_type = str(event.event)
        self._logger.warning(
            self._log_event,
            extra={
                "session_id": session_id,
                "agent_id": agent_id,
                "dropped_event_type": dropped_event_type,
                "queue_depth": queue.qsize(),
                **extra_log_fields,
            },
        )
        now = time.monotonic()
        last = self._last_marker.get(key, 0.0)
        if now - last < self._marker_interval:
            # Rate-limited: counter accumulates; marker emission deferred.
            return
        marker = StreamEvent(
            event=self._marker_event_type,
            data={
                "reason": "queue_overflow",
                "dropped": self._drops[key],
                "agent_id": agent_id,
            },
        )
        try:
            queue.put_nowait(marker)
        except asyncio.QueueFull:
            # Marker itself could not enqueue \u2014 leave timestamp untouched
            # so the next publish landing on a drained queue can emit one.
            return
        self._last_marker[key] = now
        self._drops[key] = 0


__all__ = [
    "BoundedEventChannel",
    "DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS",
]
