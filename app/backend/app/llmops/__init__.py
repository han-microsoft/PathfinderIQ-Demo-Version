"""LLMOps package — tracing, cost estimation, and export backends.

Package role:
    Separate LLMOps concerns (token usage, cost, prompt/completion audit)
    from infrastructure observability (HTTP spans, DB latency, tool duration).
    Lives alongside ``app/observability/``, not inside it.

Public API:
    from app.llmops import configure_llmops
    from app.llmops._protocol import LLMTrace
    from app.llmops._manager import LLMOpsTraceManager
    from app.llmops._cost import estimate_cost

Key collaborators:
    - ``app.config.settings``         — reads llmops_backend
    - ``app.main``                     — calls configure_llmops() in lifespan
    - ``app.deps``                     — get_llmops() dependency
    - ``app.routers.chat``             — emits traces after each turn
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def configure_llmops():
    """Create and start an LLMOpsTraceManager from LLMOPS_BACKEND env var.

    Supported backends:
        ""       — disabled (default). Returns None, zero overhead.
        "jsonl"  — append to local llmops_traces.jsonl file.
        "cosmos" — write to Cosmos DB container (future).

    Returns:
        LLMOpsTraceManager if a backend is configured, None otherwise.

    Side effects:
        - Spawns a background asyncio.Task for the export worker.
        - Logs the selected backend at INFO level.

    Dependents:
        Called by: app.main lifespan (Phase 1, after LLM service).
    """
    from app.llmops._manager import LLMOpsTraceManager

    backend = os.getenv("LLMOPS_BACKEND", "").lower()
    if not backend:
        return None

    if backend == "jsonl":
        from app.llmops._exporters.jsonl import JSONLExporter
        exporter = JSONLExporter()
    else:
        logger.error(
            "Unknown LLMOPS_BACKEND='%s' — disabling LLMOps tracing. "
            "Supported: jsonl",
            backend,
        )
        return None

    manager = LLMOpsTraceManager(exporter)
    manager.start()
    logger.info("LLMOps tracing enabled (backend=%s)", backend)
    return manager

