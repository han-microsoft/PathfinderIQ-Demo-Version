"""Conversation observability — tracing + metrics tests.

Tests the ``_tracing.py`` module from ``app.services.conversation``.
Verifies that OTel span and metric helpers work correctly, including
noop fallbacks when OTel is not configured.
"""

import pytest

from app.services.conversation._tracing import (
    _NoopCounter,
    _NoopHistogram,
    _NoopMeter,
    _NoopSpan,
    _NoopTracer,
    record_context_utilization,
    record_turn_complete,
)


class TestNoopFallbacks:
    """Noop classes work without error."""

    def test_noop_span_set_attribute(self):
        """NoopSpan.set_attribute does not raise."""
        span = _NoopSpan()
        span.set_attribute("key", "value")

    def test_noop_span_set_status(self):
        """NoopSpan.set_status does not raise."""
        span = _NoopSpan()
        span.set_status("ok")

    def test_noop_tracer_yields_span(self):
        """NoopTracer yields a NoopSpan."""
        tracer = _NoopTracer()
        with tracer.start_as_current_span("test") as span:
            assert isinstance(span, _NoopSpan)

    def test_noop_meter_creates_counter(self):
        """NoopMeter creates NoopCounter."""
        meter = _NoopMeter()
        counter = meter.create_counter("test")
        assert isinstance(counter, _NoopCounter)

    def test_noop_meter_creates_histogram(self):
        """NoopMeter creates NoopHistogram."""
        meter = _NoopMeter()
        hist = meter.create_histogram("test")
        assert isinstance(hist, _NoopHistogram)

    def test_noop_counter_add(self):
        """NoopCounter.add does not raise."""
        counter = _NoopCounter()
        counter.add(1)
        counter.add(5, {"status": "complete"})

    def test_noop_histogram_record(self):
        """NoopHistogram.record does not raise."""
        hist = _NoopHistogram()
        hist.record(0.5)
        hist.record(1.0, {"key": "val"})


class TestMetricRecording:
    """Metric recording functions do not raise."""

    def test_record_turn_complete(self):
        """record_turn_complete does not raise."""
        record_turn_complete(
            status="complete",
            duration_seconds=1.5,
            tool_call_count=3,
        )

    def test_record_context_utilization(self):
        """record_context_utilization does not raise."""
        record_context_utilization(
            tokens_used=5000,
            tokens_budget=10000,
            messages_dropped=2,
        )

    def test_record_context_utilization_zero_budget(self):
        """Zero budget does not cause division by zero."""
        record_context_utilization(
            tokens_used=0,
            tokens_budget=0,
            messages_dropped=0,
        )
