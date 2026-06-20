"""agentkit.observability — domain-blind OTel + structured-logging plumbing.

Public API (the symbols every consumer imports):

    from agentkit.observability import configure          # composition root, once
    from agentkit.observability import shutdown_observability
    from agentkit.observability import traced_tool         # @decorator on tools
    from agentkit.observability import get_tracer           # manual spans
    from agentkit.observability import get_meter            # manual metrics

What it provides:
    - OTel TracerProvider / MeterProvider bootstrap (``_bootstrap``)
    - The ``@traced_tool`` decorator (``_tracing``) — span + log + metric per call
    - Tool-call counters / duration histogram (``_metrics``)
    - Structured JSON logging (``_logging``)
    - Correlation-ID ASGI middleware + contextvar (``_middleware``)
    - Per-invocation LLM trace records + cost (``agentkit.observability.llmops``)

Layer rule:
    Imports only ``agentkit.config``, stdlib, ``fastapi`` (already a base dep),
    and the optional OTel / json-logger SDKs (``[otel]`` extra; lazy where
    heavy). NEVER imports a GridIQ package. Domain labels (service name, meter
    namespace) are injected by the composition root via ``set_service_name`` /
    ``set_metric_namespace`` (inc6 configurable-hook pattern).
"""

from __future__ import annotations

from agentkit.observability._bootstrap import (
    configure,
    set_service_name,
    shutdown_observability,
)
from agentkit.observability._metrics import (
    get_meter,
    get_tool_call_counter,
    get_tool_duration_histogram,
    get_tool_error_counter,
    set_metric_namespace,
)
from agentkit.observability._tracing import get_tracer, traced_tool

__all__ = [
    "configure",
    "shutdown_observability",
    "set_service_name",
    "traced_tool",
    "get_tracer",
    "get_meter",
    "get_tool_call_counter",
    "get_tool_duration_histogram",
    "get_tool_error_counter",
    "set_metric_namespace",
]
