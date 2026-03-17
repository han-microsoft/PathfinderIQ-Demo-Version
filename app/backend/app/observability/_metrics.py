"""Metric instruments — defined once, used where needed.

Module role:
    Centralises all OTel metric instrument definitions.  Modules that need to
    record a metric import the specific instrument:

        from app.observability._metrics import tool_call_counter
        tool_call_counter.add(1, {"tool.name": "query_graph"})

    When ``OTEL_EXPORT_TARGET=""`` (noop mode), all instruments are ``Noop*``
    instances — ``add()`` and ``record()`` are instant no-ops with zero
    allocation overhead.  This is guaranteed by the OTel SDK spec.

Key collaborators:
    - ``_tracing.py`` — ``@traced_tool`` increments counters and records histograms
    - ``_bootstrap.py`` — sets the global ``MeterProvider`` (noop or real)

Dependents:
    Imported by: ``_tracing.py``, any module needing manual metric recording
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


def get_meter(name: str = __name__) -> Any:
    """Return an OTel ``Meter``.  Returns ``NoopMeter`` when export is disabled.

    Parameters:
        name: Meter name — typically ``__name__`` of the calling module.

    Returns:
        An OTel ``Meter`` instance bound to the global ``MeterProvider``.
    """
    return metrics.get_meter(name)


# ── Pre-defined instruments ──────────────────────────────────────────────────
# Created at import time.  When the MeterProvider is Noop (default), these are
# zero-cost stubs.  When a real exporter is wired (Phase 1 console / azure /
# otlp), these become live instruments that export on the metric reader's
# interval.

_meter = get_meter("graph_demo")

# Counters — monotonically increasing totals
tool_call_counter = _meter.create_counter(
    "tool.calls",
    description="Total tool invocations",
)
tool_error_counter = _meter.create_counter(
    "tool.errors",
    description="Total tool errors",
)

# Histograms — distribution of values
tool_duration_histogram = _meter.create_histogram(
    "tool.duration_ms",
    description="Tool call duration in milliseconds",
)
