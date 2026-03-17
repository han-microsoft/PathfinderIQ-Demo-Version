"""LLMOps trace manager — async queue + background export worker.

Module role:
    Decouples trace creation (in the request path) from trace export (background).
    The request path calls ``await manager.trace(llm_trace)`` which enqueues
    without blocking. A background ``asyncio.Task`` dequeues and exports via
    the configured ``TraceExporter``.

    Queue overflow is handled gracefully (drop + log warning). Export failures
    are caught and logged — the worker never crashes. Graceful shutdown drains
    the queue before closing the exporter.

Lifecycle:
    ``configure_llmops()`` → ``LLMOpsTraceManager(exporter)`` →
    ``.start()`` (spawns worker) → ``.trace()`` (per request) →
    ``.close()`` (shutdown drain)

Key collaborators:
    - ``_protocol.py``           — LLMTrace model, TraceExporter protocol
    - ``__init__.py``            — configure_llmops() factory
    - ``app.main``               — start in lifespan, close in shutdown
    - ``app.routers.chat``       — calls trace() after each turn

Dependents:
    Created by: app.llmops.configure_llmops()
    Accessed via: app.state.llmops / deps.get_llmops()
"""

from __future__ import annotations

import asyncio
import logging

from app.llmops._protocol import LLMTrace, TraceExporter

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
