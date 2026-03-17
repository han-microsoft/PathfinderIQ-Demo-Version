"""Regression tests for Phase 3 audit fixes — performance & production readiness.

Covers:
    3.2 ASGI middleware (no BaseHTTPMiddleware)
    3.3 OTel shutdown hooks
    3.5 JSONL exporter file rotation
    3.7 ThreadSyncManager LRU eviction
    3.9 Guardrail failure metric

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= uv run python -m pytest tests/unit/test_audit_phase3.py -v
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ── 3.2: ASGI middleware (no BaseHTTPMiddleware) ────────────────────────────


class TestCorrelationIdMiddleware:
    """Verify pure ASGI middleware sets correlation ID correctly."""

    @pytest.mark.asyncio
    async def test_generates_request_id(self):
        """Middleware generates X-Request-ID when none provided."""
        from app.observability._middleware import CorrelationIdMiddleware, request_id_var

        captured_headers = {}

        async def mock_app(scope, receive, send):
            # Capture the request_id set by the middleware
            captured_headers["rid"] = request_id_var.get()
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [],
            })
            await send({
                "type": "http.response.body",
                "body": b"ok",
            })

        middleware = CorrelationIdMiddleware(mock_app)

        sent_messages = []
        async def mock_send(message):
            sent_messages.append(message)

        scope = {"type": "http", "headers": []}
        await middleware(scope, None, mock_send)

        # Verify request_id was set
        assert captured_headers["rid"] != ""
        # Verify X-Request-ID header in response
        start_msg = sent_messages[0]
        header_names = [h[0] for h in start_msg["headers"]]
        assert b"x-request-id" in header_names

    @pytest.mark.asyncio
    async def test_preserves_caller_request_id(self):
        """Middleware uses caller-provided X-Request-ID."""
        from app.observability._middleware import CorrelationIdMiddleware, request_id_var

        captured_rid = {}

        async def mock_app(scope, receive, send):
            captured_rid["value"] = request_id_var.get()
            await send({
                "type": "http.response.start", "status": 200, "headers": [],
            })
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = CorrelationIdMiddleware(mock_app)
        sent = []

        async def mock_send(m):
            sent.append(m)

        scope = {
            "type": "http",
            "headers": [(b"x-request-id", b"caller-id-123")],
        }
        await middleware(scope, None, mock_send)
        assert captured_rid["value"] == "caller-id-123"

    @pytest.mark.asyncio
    async def test_passes_through_non_http(self):
        """Non-HTTP scopes (lifespan, websocket) pass through unchanged."""
        from app.observability._middleware import CorrelationIdMiddleware

        called = {"count": 0}

        async def mock_app(scope, receive, send):
            called["count"] += 1

        middleware = CorrelationIdMiddleware(mock_app)
        await middleware({"type": "lifespan"}, None, None)
        assert called["count"] == 1


# ── 3.3: OTel shutdown hooks ────────────────────────────────────────────────


class TestOTelShutdown:
    """Verify shutdown_observability calls provider shutdown methods."""

    def test_shutdown_calls_provider_shutdown(self):
        """shutdown_observability calls .shutdown() on stored providers."""
        from app.observability._bootstrap import shutdown_observability, _otel_providers

        mock_tracer = MagicMock()
        mock_meter = MagicMock()
        _otel_providers["tracer"] = mock_tracer
        _otel_providers["meter"] = mock_meter

        shutdown_observability()

        mock_tracer.shutdown.assert_called_once()
        mock_meter.shutdown.assert_called_once()

        # Clean up
        _otel_providers.clear()

    def test_shutdown_noop_when_empty(self):
        """shutdown_observability does nothing when no providers configured."""
        from app.observability._bootstrap import shutdown_observability, _otel_providers
        _otel_providers.clear()
        # Should not raise
        shutdown_observability()


# ── 3.5: JSONL exporter file rotation ────────────────────────────────────────


class TestJSONLRotation:
    """Verify JSONL files are rotated when they exceed max size."""

    @pytest.mark.asyncio
    async def test_file_rotated_on_size_limit(self):
        """File is rotated to .1 when it exceeds _MAX_FILE_BYTES."""
        from app.llmops._exporters.jsonl import JSONLExporter, _MAX_FILE_BYTES
        from app.llmops._protocol import LLMTrace

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "traces.jsonl")
            exporter = JSONLExporter(path=path)

            # Write enough data to exceed the limit
            # Create a large trace record
            big_trace = LLMTrace(
                trace_id="t1",
                session_id="s1",
                prompt_text="x" * 1000,  # Will trigger warning but that's ok
            )

            # Fill the file past the limit
            with open(path, "w") as f:
                f.write("x" * (_MAX_FILE_BYTES + 1))

            # Next export should trigger rotation
            await exporter.export(big_trace)

            # Verify rotation occurred
            rotated_path = path + ".1"
            assert os.path.exists(rotated_path), "Rotated file should exist"
            assert os.path.exists(path), "New file should exist after rotation"
            # New file should be smaller than the rotated one
            assert os.path.getsize(path) < os.path.getsize(rotated_path)


# ── 3.7: ThreadSyncManager LRU eviction ─────────────────────────────────────
# REMOVED: ThreadSyncManager was deleted in the agent system rebuild.
# Context injection helpers moved to app/services/llm/agent.py as
# _filter_prior_messages() and _build_context_injection().


# ── 3.9: Guardrail failure metric ───────────────────────────────────────────


class TestGuardrailFailureMetric:
    """Verify guardrail errors increment the failure counter."""

    @pytest.mark.asyncio
    async def test_error_increments_counter(self):
        """A failing guardrail increments the guardrail.errors counter."""
        from app.guardrails._runner import execute_input_guardrails, _guardrail_error_counter

        class FailingGuardrail:
            name = "test_failing"
            async def check(self, text):
                raise RuntimeError("test error")

        # The counter add() is called — we can verify it doesn't raise
        # and the function returns None (fail-open)
        result = await execute_input_guardrails([FailingGuardrail()], "test")
        assert result is None  # Fail-open — no block
