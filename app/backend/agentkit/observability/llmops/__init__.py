"""agentkit.observability.llmops — per-invocation LLM trace records + cost.

Distinct from the infrastructure spans/metrics in the parent package. Captures
token counts, cost, tool calls, and optional prompt/completion text per LLM
invocation, then exports them off the request path via a background worker.

Public API:
    from agentkit.observability.llmops import configure_llmops
    from agentkit.observability.llmops import LLMTrace, TraceExporter
    from agentkit.observability.llmops import LLMOpsTraceManager
    from agentkit.observability.llmops import estimate_cost

Settings seam:
    ``configure_llmops()`` reads ``agentkit.config.get_settings().llmops_backend``
    (a ``BaseAgentSettings`` field) — never a GridIQ package.

Layer rule:
    stdlib + pydantic + ``agentkit.config`` only. Domain-blind.
"""

from __future__ import annotations

import logging

from agentkit.config.settings import get_settings
from agentkit.observability.llmops._cost import estimate_cost
from agentkit.observability.llmops._manager import LLMOpsTraceManager
from agentkit.observability.llmops._protocol import LLMTrace, TraceExporter

logger = logging.getLogger(__name__)

__all__ = [
    "configure_llmops",
    "estimate_cost",
    "LLMOpsTraceManager",
    "LLMTrace",
    "TraceExporter",
]


def configure_llmops():
    """Create and start an ``LLMOpsTraceManager`` from ``settings.llmops_backend``.

    Supported backends:
        ""       — disabled (default). Returns None, zero overhead.
        "jsonl"  — append to local llmops_traces.jsonl file.

    Returns:
        LLMOpsTraceManager if a backend is configured, None otherwise.

    Side effects:
        - Spawns a background asyncio.Task for the export worker.
        - Logs the selected backend at INFO level.
    """
    backend = (get_settings().llmops_backend or "").lower()
    if not backend:
        return None

    if backend == "jsonl":
        from agentkit.observability.llmops._exporters.jsonl import JSONLExporter
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
