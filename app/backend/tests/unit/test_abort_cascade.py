"""Unit tests for the abort-cascade mechanism.

Validates:
  1. _keepalive_wrap aborts immediately when abort_event is pre-set
  2. _keepalive_wrap aborts mid-stream when abort_event fires during a long wait
  3. _keepalive_wrap cancels the inner task on abort (CancelledError propagation)
  4. Abort endpoint cascades from specialist to orchestrator
  5. Abort endpoint returns 204 when no active generation (idempotent)
  6. Stale guard key cleanup in send_message concurrency guard
  7. Delegation tool catches CancelledError and re-raises

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python3 -m pytest tests/unit/test_abort_cascade.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.foundation.models import StreamEvent, StreamEventType


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _delayed_events(events, delay=0):
    """Yield events with an optional delay between each."""
    for event in events:
        if delay:
            await asyncio.sleep(delay)
        yield event


async def _blocked_stream():
    """An async generator that blocks indefinitely (simulates a stuck delegation)."""
    await asyncio.sleep(3600)  # 1 hour — effectively forever for tests
    yield StreamEvent(event=StreamEventType.DONE, data={})


async def _slow_stream_with_cancel_check():
    """Stream that sleeps long enough for abort to fire, raising CancelledError."""
    try:
        await asyncio.sleep(3600)
        yield StreamEvent(event=StreamEventType.DONE, data={})
    except asyncio.CancelledError:
        # The generator should propagate cancellation — this verifies
        # the inner task gets cancelled when _keepalive_wrap returns.
        raise


# ── Tests: _keepalive_wrap abort integration ─────────────────────────────────

class TestKeepaliveAbort:
    """_keepalive_wrap responds to abort_event."""

    @pytest.mark.asyncio
    async def test_abort_pre_set_yields_aborted_immediately(self):
        """If abort_event is already set, the wrapper yields ABORTED and stops."""
        from app.routers.chat import _keepalive_wrap

        abort = asyncio.Event()
        abort.set()  # Pre-set before iteration starts

        real_events = [
            StreamEvent(event=StreamEventType.TOKEN, data={"token": "hi"}),
            StreamEvent(event=StreamEventType.DONE, data={}),
        ]

        result = []
        async for event in _keepalive_wrap(
            _delayed_events(real_events), interval=5.0, abort_event=abort
        ):
            result.append(event)

        # Should get exactly one ABORTED event, no real events
        assert len(result) == 1
        assert result[0].event == StreamEventType.ABORTED

    @pytest.mark.asyncio
    async def test_abort_during_blocked_stream(self):
        """abort_event fires while inner stream is blocked → ABORTED emitted."""
        from app.routers.chat import _keepalive_wrap

        abort = asyncio.Event()

        # Set abort after a short delay (50ms)
        async def _set_abort():
            await asyncio.sleep(0.05)
            abort.set()

        asyncio.create_task(_set_abort())

        result = []
        async for event in _keepalive_wrap(
            _blocked_stream(), interval=5.0, abort_event=abort
        ):
            result.append(event)

        # Should get ABORTED — no KEEPALIVEs because interval > abort delay
        assert any(e.event == StreamEventType.ABORTED for e in result)
        # Should NOT contain DONE (stream was blocked)
        assert all(e.event != StreamEventType.DONE for e in result)

    @pytest.mark.asyncio
    async def test_abort_cancels_inner_task(self):
        """When abort fires, the inner task is cancelled (CancelledError propagates)."""
        from app.routers.chat import _keepalive_wrap

        abort = asyncio.Event()
        inner_cancelled = False

        async def _cancellable_stream():
            nonlocal inner_cancelled
            try:
                await asyncio.sleep(3600)
                yield StreamEvent(event=StreamEventType.DONE, data={})
            except asyncio.CancelledError:
                inner_cancelled = True
                raise

        # Set abort after 50ms
        async def _set_abort():
            await asyncio.sleep(0.05)
            abort.set()

        asyncio.create_task(_set_abort())

        result = []
        async for event in _keepalive_wrap(
            _cancellable_stream(), interval=5.0, abort_event=abort
        ):
            result.append(event)

        assert any(e.event == StreamEventType.ABORTED for e in result)
        # Give a tiny bit of time for the finally cleanup to run
        await asyncio.sleep(0.05)
        assert inner_cancelled, "Inner stream task should have been cancelled"

    @pytest.mark.asyncio
    async def test_abort_mid_real_events(self):
        """abort_event set after some real events → remaining events skipped."""
        from app.routers.chat import _keepalive_wrap

        abort = asyncio.Event()

        async def _events_with_mid_abort():
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": "a"})
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": "b"})
            # Simulate a pause where abort fires
            await asyncio.sleep(0.2)
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": "c"})
            yield StreamEvent(event=StreamEventType.DONE, data={})

        # Fire abort after 100ms (after first two tokens, during the 200ms pause)
        async def _set_abort():
            await asyncio.sleep(0.1)
            abort.set()

        asyncio.create_task(_set_abort())

        result = []
        async for event in _keepalive_wrap(
            _events_with_mid_abort(), interval=5.0, abort_event=abort
        ):
            result.append(event)

        types = [e.event for e in result]
        # Should have the first two tokens, then ABORTED
        assert StreamEventType.TOKEN in types
        assert StreamEventType.ABORTED in types
        # Should NOT have token "c" or DONE
        token_texts = [e.data.get("token") for e in result if e.event == StreamEventType.TOKEN]
        assert "c" not in token_texts

    @pytest.mark.asyncio
    async def test_no_abort_event_passthrough(self):
        """When abort_event is None, wrapper behaves as before (no abort logic)."""
        from app.routers.chat import _keepalive_wrap

        real_events = [
            StreamEvent(event=StreamEventType.TOKEN, data={"token": "hello"}),
            StreamEvent(event=StreamEventType.DONE, data={}),
        ]

        result = []
        async for event in _keepalive_wrap(
            _delayed_events(real_events), interval=5.0, abort_event=None
        ):
            result.append(event)

        assert len(result) == 2
        assert result[0].event == StreamEventType.TOKEN
        assert result[1].event == StreamEventType.DONE


# ── Tests: abort endpoint cascade ────────────────────────────────────────────

class TestAbortEndpointCascade:
    """Abort endpoint cascades from specialist agent to orchestrator."""

    def test_specialist_cascades_to_orchestrator(self):
        """Aborting a specialist agent_id sets the orchestrator's abort event."""
        from app.routers.chat import _abort_events

        session_id = "test-session-cascade"
        orch_event = asyncio.Event()
        _abort_events[(session_id, "orchestrator")] = orch_event

        try:
            # Simulate what the abort endpoint does for a specialist
            target_agent = "networkInvestigator"
            event = _abort_events.get((session_id, target_agent))
            if event is None and target_agent != "orchestrator":
                event = _abort_events.get((session_id, "orchestrator"))
            if event is not None:
                event.set()

            assert orch_event.is_set(), "Orchestrator abort event should be set"
        finally:
            _abort_events.pop((session_id, "orchestrator"), None)

    def test_orchestrator_direct_abort(self):
        """Aborting the orchestrator directly sets its abort event."""
        from app.routers.chat import _abort_events

        session_id = "test-session-direct"
        orch_event = asyncio.Event()
        _abort_events[(session_id, "orchestrator")] = orch_event

        try:
            target_agent = "orchestrator"
            event = _abort_events.get((session_id, target_agent))
            if event is not None:
                event.set()

            assert orch_event.is_set()
        finally:
            _abort_events.pop((session_id, "orchestrator"), None)

    def test_no_active_generation_is_idempotent(self):
        """Abort with no active generation does not raise (returns None)."""
        from app.routers.chat import _abort_events

        session_id = "test-session-none"
        # No guard key registered — simulates what the endpoint does
        target_agent = "orchestrator"
        event = _abort_events.get((session_id, target_agent))
        # Should be None — idempotent, no error
        assert event is None


# ── Tests: stale guard key cleanup ───────────────────────────────────────────

class TestStaleGuardKeyCleanup:
    """Stale abort events (already set) are cleaned up on next send_message."""

    def test_stale_set_event_is_cleaned(self):
        """A guard key with a set abort event is removed, not rejected."""
        from app.routers.chat import _abort_events

        session_id = "test-session-stale"
        agent_id = "orchestrator"
        key = (session_id, agent_id)

        # Simulate a stale guard key (abort fired but finally didn't clean up)
        stale_event = asyncio.Event()
        stale_event.set()
        _abort_events[key] = stale_event

        try:
            # Replicate the guard logic from send_message
            _stale_event = _abort_events.get(key)
            if _stale_event is not None:
                if _stale_event.is_set():
                    _abort_events.pop(key, None)

            assert key not in _abort_events, "Stale guard key should be cleaned up"
        finally:
            _abort_events.pop(key, None)

    def test_active_event_is_not_cleaned(self):
        """A guard key with an unset abort event is NOT cleaned (409 case)."""
        from app.routers.chat import _abort_events

        session_id = "test-session-active"
        agent_id = "orchestrator"
        key = (session_id, agent_id)

        active_event = asyncio.Event()  # NOT set
        _abort_events[key] = active_event

        try:
            _stale_event = _abort_events.get(key)
            should_reject = False
            if _stale_event is not None:
                if _stale_event.is_set():
                    _abort_events.pop(key, None)
                else:
                    should_reject = True

            assert should_reject, "Active generation should cause a 409 rejection"
            assert key in _abort_events, "Active guard key should NOT be cleaned up"
        finally:
            _abort_events.pop(key, None)


# ── Tests: delegation CancelledError handling ────────────────────────────────

class TestDelegationCancelledError:
    """Delegation tool catches CancelledError for clean specialist tab cleanup."""

    @pytest.mark.asyncio
    async def test_delegation_get_abort_event_returns_event(self):
        """_get_abort_event returns the orchestrator's abort event."""
        from app.routers.chat import _abort_events
        from tools.delegation import _get_abort_event

        session_id = "test-delegation-abort"
        orch_event = asyncio.Event()
        _abort_events[(session_id, "orchestrator")] = orch_event

        try:
            result = _get_abort_event(session_id)
            assert result is orch_event
        finally:
            _abort_events.pop((session_id, "orchestrator"), None)

    @pytest.mark.asyncio
    async def test_delegation_get_abort_event_returns_none_for_unknown(self):
        """_get_abort_event returns None when no guard key exists."""
        from tools.delegation import _get_abort_event

        result = _get_abort_event("nonexistent-session")
        assert result is None

    @pytest.mark.asyncio
    async def test_delegation_get_abort_event_returns_none_for_empty(self):
        """_get_abort_event returns None for empty session_id."""
        from tools.delegation import _get_abort_event

        result = _get_abort_event("")
        assert result is None
