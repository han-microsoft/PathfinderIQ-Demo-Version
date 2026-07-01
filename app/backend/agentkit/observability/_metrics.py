"""Metric instruments — defined once, used where needed.

Module role:
    Centralises all OTel metric instrument definitions.  Modules that need to
    record a metric import the specific instrument accessor:

        from agentkit.observability._metrics import get_tool_call_counter
        get_tool_call_counter().add(1, {"tool.name": "query_graph"})

    When OTel export is disabled (noop mode), all instruments are ``Noop*``
    instances — ``add()`` and ``record()`` are instant no-ops with zero
    allocation overhead.  This is guaranteed by the OTel SDK spec.

Metric namespace seam:
    The meter namespace is a consumer-supplied label (the OTel meter name).
    agentkit defaults it to ``"agentkit"``; the composition root may override
    it via :func:`set_metric_namespace` so dashboards attribute the metrics
    to the host application. Kept domain-blind — no GridIQ vocabulary here.

Layer rule:
    stdlib + optional ``opentelemetry`` only. Domain-blind.

Key collaborators:
    - ``_tracing.py`` — ``@traced_tool`` increments counters and records histograms
    - ``_bootstrap.py`` — sets the global ``MeterProvider`` (noop or real)
"""

from __future__ import annotations

from typing import Any

try:
    from opentelemetry import metrics
except ModuleNotFoundError:
    class _NoopCounter:
        """Fallback counter used when the OTel package is unavailable."""

        def add(self, amount: int, attributes: dict[str, str] | None = None) -> None:
            """Discard metric writes in noop mode."""
            return None

    class _NoopHistogram:
        """Fallback histogram used when the OTel package is unavailable."""

        def record(self, amount: int, attributes: dict[str, str] | None = None) -> None:
            """Discard metric writes in noop mode."""
            return None

    class _NoopMeter:
        """Fallback meter that manufactures noop instruments."""

        def create_counter(self, name: str, description: str = "") -> _NoopCounter:
            """Return a noop counter for callers expecting an OTel instrument."""
            return _NoopCounter()

        def create_histogram(self, name: str, description: str = "") -> _NoopHistogram:
            """Return a noop histogram for callers expecting an OTel instrument."""
            return _NoopHistogram()

    class _NoopMetricsModule:
        """Small compatibility layer that mimics the subset of metrics API we use."""

        Meter = _NoopMeter

        @staticmethod
        def get_meter(name: str) -> _NoopMeter:
            """Return a noop meter when observability dependencies are absent."""
            return _NoopMeter()

    metrics = _NoopMetricsModule()


# ── Metric-namespace seam (inc6 configurable-hook pattern) ───────────────────
# The OTel meter name under which the shared tool instruments are created. The
# composition root may override the generic default so dashboards attribute the
# metrics to the host application.
_metric_namespace: str = "agentkit"


def set_metric_namespace(name: str) -> None:
    """Register the OTel meter namespace used for the shared tool instruments.

    Called by the composition root before the first traced tool invocation.
    Idempotent until the instruments are first created (lazy in the getters).
    """
    global _metric_namespace
    _metric_namespace = name


def get_meter(name: str = __name__) -> Any:
    """Return an OTel ``Meter``.  Returns ``NoopMeter`` when export is disabled.

    Parameters:
        name: Meter name — typically ``__name__`` of the calling module.

    Returns:
        An OTel ``Meter`` instance bound to the global ``MeterProvider``.
    """
    return metrics.get_meter(name)


_tool_call_counter: Any | None = None
_tool_error_counter: Any | None = None
_tool_duration_histogram: Any | None = None


def get_tool_call_counter() -> Any:
    """Return the shared tool-invocation counter.

    Purpose:
        Delays instrument creation until the first traced tool invocation so
        imports stay side-effect free when observability is unused.
    """
    global _tool_call_counter
    if _tool_call_counter is None:
        _tool_call_counter = get_meter(_metric_namespace).create_counter(
            "tool.calls",
            description="Total tool invocations",
        )
    return _tool_call_counter


def get_tool_error_counter() -> Any:
    """Return the shared tool-error counter."""
    global _tool_error_counter
    if _tool_error_counter is None:
        _tool_error_counter = get_meter(_metric_namespace).create_counter(
            "tool.errors",
            description="Total tool errors",
        )
    return _tool_error_counter


def get_tool_duration_histogram() -> Any:
    """Return the shared tool-duration histogram."""
    global _tool_duration_histogram
    if _tool_duration_histogram is None:
        _tool_duration_histogram = get_meter(_metric_namespace).create_histogram(
            "tool.duration_ms",
            description="Tool call duration in milliseconds",
        )
    return _tool_duration_histogram
