"""Per-(session, agent) single-flight + abort event registry (S4).

Module role:
    The generic in-process abort spine. Holds the dict of active
    generation abort events, keyed by ``(session_id, agent_id)``, and a
    single-flight claim helper (``try_register_abort_event``) so two
    concurrent generations for the same key cannot both run. Domain-blind:
    a host's chat router creates and consumes abort events; a streaming
    tool reads them to short-circuit when the parent generation is
    aborted. This module names none of those consumers.

Concurrency model:
    In-process only. The single-flight claim collapses check + register
    into one sync section so the event loop cannot interleave a competing
    claim. It does NOT survive across processes/replicas.

    # TODO(B-CHAOS-025): distributed lease. Under multi-replica hosting
    # the in-process dict is per-replica, so two replicas can each claim
    # the same (session, agent) slot (cross-replica TOCTOU). A future
    # increment replaces the dict claim with a distributed lease (e.g. a
    # Cosmos / Redis lease with TTL) behind this same function signature
    # so callers do not change. Until then single-flight is best-effort
    # within one replica.
"""

from __future__ import annotations

import asyncio
import time

# Active generation abort events, keyed by (session_id, agent_id).
# Set by the chat router when a generation starts; checked by the
# delegation tool and keepalive wrapper during streaming.
abort_events: dict[tuple[str, str], asyncio.Event] = {}

# Timestamps for when each abort event was registered. Used by
# cleanup_stale_entries() to evict orphaned entries (fix #16).
_abort_timestamps: dict[tuple[str, str], float] = {}


def register_abort_event(key: tuple[str, str], event: asyncio.Event) -> None:
    """Register an abort event with a timestamp for TTL-based cleanup."""
    abort_events[key] = event
    _abort_timestamps[key] = time.monotonic()


def unregister_abort_event(key: tuple[str, str]) -> None:
    """Remove an abort event and its timestamp."""
    abort_events.pop(key, None)
    _abort_timestamps.pop(key, None)


def try_register_abort_event(
    key: tuple[str, str], event: asyncio.Event
) -> asyncio.Event | None:
    """Atomic claim of a (session, agent) generation slot.

    Chaos hardening 2026-05-22 (CHAOS-025): the old check-then-register
    pattern in the chat router was TOCTOU — five parallel sends all
    read ``abort_events.get(key)`` as ``None`` before any of them
    reached the register call, so all five claimed the slot. This
    helper collapses the check and the registration into a single
    sync section (no ``await`` between read and write) so the event
    loop cannot interleave a competing send.

    Returns:
        ``None`` if the caller has claimed the slot (caller MUST
        eventually call ``unregister_abort_event`` to release it).
        The existing live ``asyncio.Event`` if a generation is already
        in flight (caller MUST raise 409 — the slot is not theirs).
        A stale ``abort_events`` entry whose event ``is_set()`` is
        treated as released and overwritten in-place.
    """
    existing = abort_events.get(key)
    if existing is not None and not existing.is_set():
        return existing
    abort_events[key] = event
    _abort_timestamps[key] = time.monotonic()
    return None


def cleanup_stale_entries(max_age_seconds: float = 600.0) -> int:
    """Evict abort entries older than max_age_seconds.

    Called periodically to prevent orphaned entries from blocking
    future messages with 409 errors. Default TTL is 600s (2× the
    default CHAT_TIMEOUT_SECONDS of 300s).

    Returns:
        Number of entries evicted.
    """
    now = time.monotonic()
    stale_keys = [
        k for k, t in _abort_timestamps.items()
        if (now - t) > max_age_seconds
    ]
    for k in stale_keys:
        abort_events.pop(k, None)
        _abort_timestamps.pop(k, None)
    return len(stale_keys)
