"""Unit tests for the SSE keepalive wrapper in routers/chat.py.

Validates that _keepalive_wrap injects KEEPALIVE events during silence
and passes through real events transparently.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python -m pytest tests/unit/test_keepalive.py -v
"""

import asyncio

import pytest

from app.foundation.models import StreamEvent, StreamEventType


async def _delayed_events(events, delay=0):
    """Yield events with an optional delay between each."""
    for event in events:
        if delay:
            await asyncio.sleep(delay)
        yield event


class TestKeepaliveWrap:
    """Verify _keepalive_wrap injects heartbeats during silence."""

    async def test_passthrough_without_silence(self):
        """Real events pass through unchanged when they arrive fast."""
        from app.routers.chat import _keepalive_wrap

        real_events = [
            StreamEvent(event=StreamEventType.TOKEN, data={"token": "hello"}),
            StreamEvent(event=StreamEventType.TOKEN, data={"token": " world"}),
            StreamEvent(event=StreamEventType.DONE, data={}),
        ]

        result = []
        async for event in _keepalive_wrap(_delayed_events(real_events), interval=5.0):
            result.append(event)

        # All 3 real events should pass through, no keepalives
        assert len(result) == 3
        assert all(e.event != StreamEventType.KEEPALIVE for e in result)
        assert result[0].data["token"] == "hello"
        assert result[2].event == StreamEventType.DONE

    async def test_keepalive_injected_during_silence(self):
        """KEEPALIVE events are injected when the inner stream is silent."""
        from app.routers.chat import _keepalive_wrap

        async def _slow_events():
            """Yield events with a 0.3s delay before each."""
            await asyncio.sleep(0.3)
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": "hi"})
            await asyncio.sleep(0.3)
            yield StreamEvent(event=StreamEventType.DONE, data={})

        result = []
        # Use a very short interval (0.1s) so keepalives fire during the 0.3s gaps
        async for event in _keepalive_wrap(_slow_events(), interval=0.1):
            result.append(event)

        # Should have at least one KEEPALIVE between the real events
        event_types = [e.event for e in result]
        assert StreamEventType.KEEPALIVE in event_types
        # First event should be a KEEPALIVE (0.1s timeout fires before 0.3s delay)
        assert event_types[0] == StreamEventType.KEEPALIVE
        # Both real events should still be present
        real_events_out = [e for e in result if e.event != StreamEventType.KEEPALIVE]
        assert len(real_events_out) == 2
        assert real_events_out[0].data["token"] == "hi"
        assert real_events_out[1].event == StreamEventType.DONE

    async def test_empty_stream_no_infinite_loop(self):
        """An immediately-exhausted stream produces no events."""
        from app.routers.chat import _keepalive_wrap

        result = []
        async for event in _keepalive_wrap(_delayed_events([]), interval=0.1):
            result.append(event)

        assert result == []

    async def test_keepalive_data_is_empty(self):
        """KEEPALIVE events carry an empty data payload."""
        from app.routers.chat import _keepalive_wrap

        real_events = [
            StreamEvent(event=StreamEventType.DONE, data={}),
        ]

        result = []
        async for event in _keepalive_wrap(
            _delayed_events(real_events, delay=0.2), interval=0.05
        ):
            result.append(event)

        keepalives = [e for e in result if e.event == StreamEventType.KEEPALIVE]
        assert len(keepalives) >= 1
        for ka in keepalives:
            assert ka.data == {}
