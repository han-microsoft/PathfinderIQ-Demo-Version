"""Error taxonomy — tests for ErrorCode, classify_error(), make_error_event().

Phase 1.4: Structured error classification so the frontend can render
error-code-specific UI (retry button, content warning, auth prompt).

Test strategy:
    - Table-driven tests for classify_error() — exception patterns → ErrorCode
    - make_error_event() produces correctly shaped StreamEvent objects
    - generate_error_id() produces valid 12-char hex strings
    - ErrorCode enum values are all lowercase snake_case strings
    - No RATE_LIMITED in ErrorCode (handled by StreamEventType.RATE_LIMITED)
"""

from __future__ import annotations

import re

import pytest


class TestErrorCodeEnum:
    """ErrorCode enum structure and values."""

    def test_enum_exists(self):
        """ErrorCode can be imported from app.foundation.errors."""
        from app.foundation.errors import ErrorCode
        assert ErrorCode is not None

    def test_values_are_lowercase_snake_case(self):
        """All ErrorCode values must be lowercase snake_case strings."""
        from app.foundation.errors import ErrorCode
        for code in ErrorCode:
            assert re.match(r"^[a-z][a-z0-9_]*$", code.value), (
                f"ErrorCode.{code.name} = '{code.value}' is not snake_case"
            )

    def test_no_rate_limited(self):
        """ErrorCode must NOT contain rate_limited — that's StreamEventType.RATE_LIMITED."""
        from app.foundation.errors import ErrorCode
        values = {e.value for e in ErrorCode}
        assert "rate_limited" not in values, (
            "rate_limited belongs in StreamEventType, not ErrorCode"
        )

    def test_expected_codes_present(self):
        """Core error codes must be defined."""
        from app.foundation.errors import ErrorCode
        expected = {
            "content_filtered", "tool_timeout", "tool_error",
            "provider_error", "auth_error", "timeout", "internal_error",
        }
        actual = {e.value for e in ErrorCode}
        missing = expected - actual
        assert not missing, f"Missing ErrorCode values: {missing}"


class TestClassifyError:
    """classify_error() maps exceptions to (ErrorCode, message) tuples."""

    def _classify(self, exc: Exception):
        from app.foundation.errors import classify_error
        return classify_error(exc)

    # ── Timeout patterns ─────────────────────────────────────────────────

    def test_timeout_exception(self):
        """asyncio.TimeoutError → TIMEOUT."""
        import asyncio
        code, msg = self._classify(asyncio.TimeoutError())
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.TIMEOUT

    def test_timeout_string(self):
        """Exception with 'timed out' → TIMEOUT."""
        code, _ = self._classify(Exception("The request timed out after 30s"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.TIMEOUT

    def test_deadline_exceeded(self):
        """Exception with 'deadline exceeded' → TIMEOUT."""
        code, _ = self._classify(Exception("gRPC deadline exceeded"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.TIMEOUT

    # ── Content filter patterns ──────────────────────────────────────────

    def test_content_filter(self):
        """Exception with 'content filter' → CONTENT_FILTERED."""
        code, _ = self._classify(Exception("content filter triggered"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.CONTENT_FILTERED

    def test_responsible_ai(self):
        """Exception with 'responsible ai' → CONTENT_FILTERED."""
        code, _ = self._classify(Exception("Responsible AI policy violation"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.CONTENT_FILTERED

    # ── Auth patterns ────────────────────────────────────────────────────

    def test_auth_401(self):
        """Exception with 'HTTP 401' → AUTH_ERROR."""
        code, _ = self._classify(Exception("HTTP 401 Unauthorized"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.AUTH_ERROR

    def test_authentication_failed(self):
        """Exception with 'authentication' → AUTH_ERROR."""
        code, _ = self._classify(Exception("Authentication token expired"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.AUTH_ERROR

    # ── Provider error patterns ──────────────────────────────────────────

    def test_provider_500(self):
        """Exception with 'HTTP 500' → PROVIDER_ERROR."""
        code, _ = self._classify(Exception("HTTP 500 Internal Server Error"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.PROVIDER_ERROR

    def test_provider_502(self):
        """Exception with 'HTTP 502' → PROVIDER_ERROR."""
        code, _ = self._classify(Exception("HTTP 502 Bad Gateway"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.PROVIDER_ERROR

    # ── Default fallback ─────────────────────────────────────────────────

    def test_unknown_exception_defaults_to_internal(self):
        """Unknown exception type → INTERNAL_ERROR."""
        code, _ = self._classify(Exception("something completely unexpected"))
        from app.foundation.errors import ErrorCode
        assert code == ErrorCode.INTERNAL_ERROR

    def test_message_is_sanitized(self):
        """Returned message must not contain raw exception details."""
        _, msg = self._classify(Exception("KeyError: 'secret_api_key'"))
        assert "secret_api_key" not in msg
        assert "KeyError" not in msg

    # ── False positive guards ────────────────────────────────────────────

    def test_429_in_message_not_rate_limit(self):
        """'429' embedded in non-HTTP context should NOT match rate limit."""
        # ErrorCode has no rate_limited — this must be INTERNAL_ERROR
        code, _ = self._classify(Exception("Processed 429 records successfully"))
        from app.foundation.errors import ErrorCode
        # Should NOT be classified as anything specific — 429 in non-HTTP context
        # The classifier should look for contextual patterns, not bare "429"
        assert code == ErrorCode.INTERNAL_ERROR


class TestMakeErrorEvent:
    """make_error_event() produces correctly shaped StreamEvent objects."""

    def test_basic_error_event(self):
        """Produces StreamEvent with ERROR type and error_code field."""
        from app.foundation.errors import ErrorCode, make_error_event
        from app.foundation.models import StreamEventType

        event = make_error_event(ErrorCode.TIMEOUT, "Request timed out.")
        assert event.event == StreamEventType.ERROR
        assert event.data["error"] == "Request timed out."
        assert event.data["error_code"] == "timeout"

    def test_error_id_included(self):
        """error_id is included when provided."""
        from app.foundation.errors import ErrorCode, make_error_event

        event = make_error_event(ErrorCode.INTERNAL_ERROR, "Oops", error_id="abc123def456")
        assert event.data["error_id"] == "abc123def456"

    def test_error_id_omitted_when_empty(self):
        """error_id key is absent when not provided."""
        from app.foundation.errors import ErrorCode, make_error_event

        event = make_error_event(ErrorCode.TIMEOUT, "Timeout")
        assert "error_id" not in event.data

    def test_retry_after_included(self):
        """retry_after is included for timeout errors."""
        from app.foundation.errors import ErrorCode, make_error_event

        event = make_error_event(ErrorCode.TIMEOUT, "Timeout", retry_after=30)
        assert event.data["retry_after"] == 30

    def test_tool_name_included(self):
        """tool_name is included for tool errors."""
        from app.foundation.errors import ErrorCode, make_error_event

        event = make_error_event(ErrorCode.TOOL_ERROR, "Query failed", tool_name="query_graph")
        assert event.data["tool_name"] == "query_graph"


class TestGenerateErrorId:
    """generate_error_id() produces valid correlation IDs."""

    def test_is_12_char_hex(self):
        """Error ID is a 12-character lowercase hex string."""
        from app.foundation.errors import generate_error_id
        eid = generate_error_id()
        assert len(eid) == 12
        assert re.match(r"^[0-9a-f]{12}$", eid)

    def test_unique_per_call(self):
        """Each call returns a different ID."""
        from app.foundation.errors import generate_error_id
        ids = {generate_error_id() for _ in range(100)}
        assert len(ids) == 100
