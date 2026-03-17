"""Conversation-level OTel span and metric helpers.

Module role:
    Provides conversation-level OpenTelemetry instrumentation:
    spans for the full turn lifecycle, and metric counters/histograms
    for conversation activity.

    All instrumentation is safe to use with the noop tracer/meter
    (when OTEL_EXPORT_TARGET is empty). Zero overhead when disabled.

Role in system:
    Part of the ``conversation`` service package. Called by ``_lifecycle.py``
    and ``_context.py`` to emit spans and metrics.

Key collaborators:
    - ``opentelemetry.trace`` — tracing API
    - ``opentelemetry.metrics`` — metrics API (optional)

Dependents:
    - ``app.services.conversation._lifecycle`` — uses span helpers
    - ``app.services.conversation._context`` — uses utilization metric
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Lazy-init tracer and meter to avoid import errors when OTel is not installed.
# These are module-level singletons, initialized on first use.
_tracer = None
_meter = None

# Metric instruments — initialized lazily
_turns_total = None
_turn_duration = None
_tool_calls_per_turn = None
_context_utilization = None
_messages_dropped = None


def _get_tracer():
    """Get or create the conversation tracer (lazy singleton).

    Returns:
        An OpenTelemetry Tracer instance. Falls back to noop tracer
        if the OTel SDK is not configured.
    """
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace
            _tracer = trace.get_tracer("app.services.conversation")
        except ImportError:
            # OTel not installed — return a noop-like object
            _tracer = _NoopTracer()
    return _tracer


def _get_meter():
    """Get or create the conversation meter (lazy singleton).

    Returns:
        An OpenTelemetry Meter instance. Falls back to noop meter
        if the OTel SDK is not configured.
    """
    global _meter
    if _meter is None:
        try:
            from opentelemetry import metrics
            _meter = metrics.get_meter("app.services.conversation")
        except ImportError:
            _meter = _NoopMeter()
    return _meter


def _ensure_instruments():
    """Initialize metric instruments on first use.

    Creates counters and histograms for conversation metrics.
    Safe to call multiple times (idempotent).
    """
    global _turns_total, _turn_duration, _tool_calls_per_turn
    global _context_utilization, _messages_dropped

    if _turns_total is not None:
        return  # Already initialized

    meter = _get_meter()
    try:
        _turns_total = meter.create_counter(
            "conversation.turns_total",
            description="Total conversation turns by status",
        )
        _turn_duration = meter.create_histogram(
            "conversation.turn_duration_seconds",
            description="Turn duration in seconds",
            unit="s",
        )
        _tool_calls_per_turn = meter.create_histogram(
            "conversation.tool_calls_per_turn",
            description="Tool calls per conversation turn",
        )
        _context_utilization = meter.create_histogram(
            "conversation.context_utilization_ratio",
            description="Token utilization ratio (0.0-1.0)",
        )
        _messages_dropped = meter.create_counter(
            "conversation.messages_dropped_total",
            description="Messages dropped by context window trimming",
        )
    except Exception:
        # If instrument creation fails, use noops
        logger.debug("OTel metric instrument creation failed — using noops")


def record_turn_complete(
    status: str,
    duration_seconds: float,
    tool_call_count: int,
) -> None:
    """Record a completed conversation turn in metrics.

    Args:
        status: Turn outcome — "complete", "error", or "aborted".
        duration_seconds: Elapsed time from start to finalization.
        tool_call_count: Number of tool calls in this turn.

    Side effects:
        Increments ``conversation.turns_total`` counter.
        Records ``conversation.turn_duration_seconds`` histogram.
        Records ``conversation.tool_calls_per_turn`` histogram.
    """
    _ensure_instruments()
    try:
        if _turns_total:
            _turns_total.add(1, {"status": status})
        if _turn_duration:
            _turn_duration.record(duration_seconds, {"status": status})
        if _tool_calls_per_turn:
            _tool_calls_per_turn.record(tool_call_count)
    except Exception:
        pass  # Metrics are best-effort — never block the request


def record_context_utilization(
    tokens_used: int,
    tokens_budget: int,
    messages_dropped: int,
) -> None:
    """Record context window utilization metrics.

    Args:
        tokens_used: Tokens consumed by the context window.
        tokens_budget: Total available token budget.
        messages_dropped: Number of messages trimmed.

    Side effects:
        Records ``conversation.context_utilization_ratio`` histogram.
        Increments ``conversation.messages_dropped_total`` counter.
    """
    _ensure_instruments()
    try:
        if _context_utilization and tokens_budget > 0:
            ratio = tokens_used / tokens_budget
            _context_utilization.record(ratio)
        if _messages_dropped and messages_dropped > 0:
            _messages_dropped.add(messages_dropped)
    except Exception:
        pass


# ── Noop fallbacks for environments without OTel ────────────────────────────


class _NoopSpan:
    """Minimal noop span for environments without OTel."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoopTracer:
    """Minimal noop tracer for environments without OTel."""

    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any):
        yield _NoopSpan()


class _NoopMeter:
    """Minimal noop meter for environments without OTel."""

    def create_counter(self, name: str, **kwargs: Any):
        return _NoopCounter()

    def create_histogram(self, name: str, **kwargs: Any):
        return _NoopHistogram()


class _NoopCounter:
    """Minimal noop counter."""

    def add(self, value: int, attributes: dict | None = None) -> None:
        pass


class _NoopHistogram:
    """Minimal noop histogram."""

    def record(self, value: float, attributes: dict | None = None) -> None:
        pass


# Eagerly initialize metric instruments at module load. OTel SDK guarantees
# noop instruments when no MeterProvider is configured — zero overhead.
# This must run after the noop classes are defined so ImportError fallbacks
# can instantiate them during module import.
_ensure_instruments()
