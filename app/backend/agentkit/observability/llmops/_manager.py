"""LLMOps trace manager — async queue + background export worker.

Decouples trace creation (request path) from trace export (background task).
``trace()`` calls ``put_nowait`` so the request path is never blocked by export
I/O. Queue overflow drops with a warning. Export failures are caught and
logged — the worker never crashes. ``close()`` drains the queue before
shutting down the exporter.

Layer rule:
    stdlib + ``agentkit.observability.llmops._protocol`` only. Domain-blind.

Lifecycle:
    ``configure_llmops()`` → ``LLMOpsTraceManager(exporter)`` →
    ``.start()`` → ``.trace()`` (per request) → ``.close()`` (shutdown).
"""

from __future__ import annotations

import asyncio
import logging

from agentkit.observability.llmops._protocol import LLMTrace, TraceExporter

logger = logging.getLogger(__name__)


class LLMOpsTraceManager:
    """Async queue + background worker for LLMOps trace export.

    The manager accepts traces via ``.trace()`` (non-blocking put_nowait)
    and exports them in a background task. This ensures the request path
    is never blocked by I/O (file writes, Cosmos calls).

    Attributes:
        last_trace: The most recently exported trace, cached for the
            ``/api/observability/status`` endpoint. Replaces the ephemeral
            ``_last_run`` dict that only the agent provider populated.
    """

    def __init__(self, exporter: TraceExporter, queue_size: int = 1000) -> None:
        """Initialize with a trace exporter and max queue depth.

        Args:
            exporter: TraceExporter implementation for the chosen backend.
            queue_size: Maximum number of queued traces before dropping.
                1000 is generous — one trace per chat turn, so this
                accommodates ~1000 concurrent users before dropping.
        """
        self._exporter = exporter
        self._queue: asyncio.Queue[LLMTrace] = asyncio.Queue(maxsize=queue_size)
        self._task: asyncio.Task | None = None
        self._closing = False
        self.last_trace: LLMTrace | None = None

    def start(self) -> None:
        """Spawn the background export worker as an asyncio.Task."""
        self._task = asyncio.create_task(self._worker(), name="llmops-exporter")

    async def trace(self, trace: LLMTrace) -> None:
        """Enqueue a trace for background export (non-blocking).

        If the queue is full, the trace is dropped and a warning is logged.
        This ensures the request path is never blocked.

        Args:
            trace: The LLMTrace record to export.
        """
        if self._closing:
            return
        try:
            self._queue.put_nowait(trace)
        except asyncio.QueueFull:
            logger.warning("llmops.queue_full — trace dropped (session=%s)", trace.session_id)

    async def _worker(self) -> None:
        """Background worker — dequeues and exports traces.

        Uses ``asyncio.wait_for`` with a 1-second timeout so the worker can
        check the ``_closing`` flag periodically and exit after the queue drains.
        Export failures are caught and logged — the worker never crashes.
        """
        while True:
            try:
                trace = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if self._closing:
                    break  # Queue empty + closing → exit
                continue  # Queue empty, not closing → keep waiting
            try:
                await self._exporter.export(trace)
                self.last_trace = trace  # Cache for observability status
            except Exception as e:
                logger.warning("llmops.export_failed: %s", e)
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        """Drain the queue, then shut down the worker and exporter.

        Waits up to 5 seconds for in-flight traces to export before
        force-cancelling the worker task. Always closes the exporter.
        """
        self._closing = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        await self._exporter.close()
