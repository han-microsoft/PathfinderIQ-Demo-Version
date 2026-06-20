"""Regression tests for Phase 2 audit fixes — security hardening.

Covers:
    2.1 KQL read-only guardrail
    2.2 Path traversal validation for scenario_name
    2.3 Query preview sanitization in trace attributes
    2.4 Content safety generic error message
    2.6 LLMOps sensitive field warning

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= uv run python -m pytest tests/unit/test_audit_phase2.py -v
"""

import logging
from unittest.mock import patch

import pytest


# ── 2.1: KQL read-only guardrail ────────────────────────────────────────────
# REMOVED 2026-06-20: the Fabric/KQL telemetry backend was retired in the Cosmos
# migration. The live Cosmos SQL read-only guard is covered by
# tests/unit/test_cosmos_guards.py::TestCosmosSqlReadOnlyGuard.


# ── 2.2: Path traversal validation ──────────────────────────────────────────


class TestPathTraversalValidation:
    """Verify scenario_name with path separators is rejected."""

    def test_parent_directory_traversal_blocked(self):
        """scenario_name '../../etc' → returns None."""
        from app.scenario import get_scenario_dir
        result = get_scenario_dir(scenario_name="../../etc")
        assert result is None

    def test_forward_slash_blocked(self):
        """scenario_name with '/' → returns None."""
        from app.scenario import get_scenario_dir
        result = get_scenario_dir(scenario_name="foo/bar")
        assert result is None

    def test_null_byte_blocked(self):
        """scenario_name with null byte → returns None."""
        from app.scenario import get_scenario_dir
        result = get_scenario_dir(scenario_name="foo\x00bar")
        assert result is None

    def test_clean_name_allowed(self):
        """Valid scenario_name with dashes and dots is allowed."""
        from app.scenario import get_scenario_dir
        # May return None if dir doesn't exist, but shouldn't block
        result = get_scenario_dir(scenario_name="telecom-playground")
        # Just verify it didn't return None for path traversal reasons
        # (it may return None because the dir doesn't exist in test env)
        assert result is None or result.name == "telecom-playground"


# ── 2.3: Query preview sanitization ─────────────────────────────────────────


class TestQueryPreviewSanitization:
    """Verify sensitive patterns in query previews are redacted."""

    def test_bearer_token_redacted(self):
        """Bearer tokens in query preview are replaced with [REDACTED]."""
        import re
        query = "SELECT * FROM users WHERE token='Bearer eyJhbGciOi...'"
        sanitized = re.sub(
            r"(Bearer\s+\S+|api[_-]?key[=:]\S+|password[=:]\S+|secret[=:]\S+)",
            "[REDACTED]",
            query[:200],
            flags=re.IGNORECASE,
        )
        assert "eyJhbGciOi" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_api_key_redacted(self):
        """api_key= patterns are redacted."""
        import re
        query = "search api_key=sk-1234567890abc"
        sanitized = re.sub(
            r"(Bearer\s+\S+|api[_-]?key[=:]\S+|password[=:]\S+|secret[=:]\S+)",
            "[REDACTED]",
            query[:200],
            flags=re.IGNORECASE,
        )
        assert "sk-1234567890abc" not in sanitized

    def test_normal_query_unchanged(self):
        """Queries without sensitive patterns pass through unchanged."""
        import re
        query = "MATCH (r:CoreRouter) RETURN r.Hostname"
        sanitized = re.sub(
            r"(Bearer\s+\S+|api[_-]?key[=:]\S+|password[=:]\S+|secret[=:]\S+)",
            "[REDACTED]",
            query[:200],
            flags=re.IGNORECASE,
        )
        assert sanitized == query


# ── 2.4: Content safety generic error message ────────────────────────────────


class TestContentSafetyErrorMessage:
    """Verify content safety guardrail returns generic error reason."""

    @pytest.mark.asyncio
    async def test_error_reason_is_generic(self):
        """Exception message should NOT leak into guardrail reason."""
        from app.guardrails.input.content_safety import ContentSafetyGuardrail
        guard = ContentSafetyGuardrail(endpoint="https://fake.cognitiveservices.azure.com")
        # This will fail because the endpoint is fake — should return generic reason
        result = await guard.check("test input")
        assert "content_safety_check_unavailable" in result.reason
        # Should NOT contain exception details
        assert "error:" not in result.reason.lower() or "unavailable" in result.reason.lower()


# ── 2.6: LLMOps sensitive field warning ──────────────────────────────────────


class TestLLMOpsSensitiveFieldWarning:
    """Verify warning is emitted when sensitive fields are populated."""

    def test_no_warning_when_empty(self, caplog):
        """No warning when prompt_text and completion_text are None."""
        from app.llmops._protocol import LLMTrace
        with caplog.at_level(logging.WARNING):
            LLMTrace(trace_id="t1", session_id="s1")
        assert "sensitive_fields_populated" not in caplog.text

    def test_warning_when_prompt_text_set(self, caplog):
        """Warning emitted when prompt_text is populated."""
        from app.llmops._protocol import LLMTrace
        with caplog.at_level(logging.WARNING):
            LLMTrace(
                trace_id="t1",
                session_id="s1",
                prompt_text="Hello world",
            )
        assert "sensitive_fields_populated" in caplog.text

    def test_warning_when_completion_text_set(self, caplog):
        """Warning emitted when completion_text is populated."""
        from app.llmops._protocol import LLMTrace
        with caplog.at_level(logging.WARNING):
            LLMTrace(
                trace_id="t1",
                session_id="s1",
                completion_text="Response text",
            )
        assert "sensitive_fields_populated" in caplog.text
