"""LLMOps manager tests — async queue, export, graceful drain.

Phase 1.1: Validates the async background worker that dequeues LLMTrace
records and exports them via a TraceExporter implementation.
"""

from __future__ import annotations

import asyncio

import pytest


class TestLLMOpsTraceManager:
    """LLMOpsTraceManager — queue, export, lifecycle."""

    @pytest.fixture
    def fake_exporter(self):
        """A fake TraceExporter that records exported traces."""
        from app.llmops._protocol import LLMTrace

        class FakeExporter:
            def __init__(self):
                self.traces: list[LLMTrace] = []
                self.closed = False

            async def export(self, trace: LLMTrace) -> None:
                self.traces.append(trace)

            async def close(self) -> None:
                self.closed = True

        return FakeExporter()

    async def test_trace_exported(self, fake_exporter):
        """Enqueued trace is exported by the background worker."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        mgr = LLMOpsTraceManager(fake_exporter)
        mgr.start()

        await mgr.trace(LLMTrace(trace_id="r1", session_id="s1"))
        # Give the worker time to process
        await asyncio.sleep(0.1)

        assert len(fake_exporter.traces) == 1
        assert fake_exporter.traces[0].trace_id == "r1"

        await mgr.close()

    async def test_multiple_traces(self, fake_exporter):
        """Multiple traces are all exported."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        mgr = LLMOpsTraceManager(fake_exporter)
        mgr.start()

        for i in range(5):
            await mgr.trace(LLMTrace(trace_id=f"r{i}", session_id="s"))
        await asyncio.sleep(0.2)

        assert len(fake_exporter.traces) == 5
        await mgr.close()

    async def test_drop_on_queue_full(self, fake_exporter):
        """When queue is full, trace is dropped (not blocked)."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        # Tiny queue that will fill immediately
        mgr = LLMOpsTraceManager(fake_exporter, queue_size=1)
        # Don't start the worker so the queue stays full
        for _ in range(10):
            await mgr.trace(LLMTrace(trace_id="r", session_id="s"))

        # Should not hang — drops silently
        await mgr.close()  # close without starting is safe

    async def test_close_drains_queue(self, fake_exporter):
        """close() waits for in-flight traces before shutting down."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        mgr = LLMOpsTraceManager(fake_exporter)
        mgr.start()

        await mgr.trace(LLMTrace(trace_id="r1", session_id="s1"))
        await mgr.close()

        assert len(fake_exporter.traces) >= 1
        assert fake_exporter.closed

    async def test_export_failure_does_not_crash(self):
        """Export failure is logged, not raised — worker continues."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        class FailingExporter:
            def __init__(self):
                self.call_count = 0
            async def export(self, trace):
                self.call_count += 1
                if self.call_count == 1:
                    raise RuntimeError("Export failed")
            async def close(self):
                pass

        exporter = FailingExporter()
        mgr = LLMOpsTraceManager(exporter)
        mgr.start()

        # First trace fails, second should still be processed
        await mgr.trace(LLMTrace(trace_id="fail", session_id="s"))
        await mgr.trace(LLMTrace(trace_id="ok", session_id="s"))
        await asyncio.sleep(0.2)

        assert exporter.call_count == 2
        await mgr.close()

    async def test_close_without_start(self):
        """Calling close() without start() does not crash."""
        from app.llmops._manager import LLMOpsTraceManager

        class NoopExporter:
            async def export(self, trace): pass
            async def close(self): pass

        mgr = LLMOpsTraceManager(NoopExporter())
        await mgr.close()  # Should not raise

    async def test_last_trace_cached(self, fake_exporter):
        """Manager caches last trace for observability status endpoint."""
        from app.llmops._manager import LLMOpsTraceManager
        from app.llmops._protocol import LLMTrace

        mgr = LLMOpsTraceManager(fake_exporter)
        mgr.start()

        await mgr.trace(LLMTrace(trace_id="r1", session_id="s1", model="gpt-4.1"))
        await asyncio.sleep(0.1)

        last = mgr.last_trace
        assert last is not None
        assert last.model == "gpt-4.1"

        await mgr.close()
