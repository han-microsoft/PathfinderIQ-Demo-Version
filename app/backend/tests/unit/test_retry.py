"""Retry module tests — rate-limit detection, backoff, model fallback queue.

Tests the shared retry primitives in app.foundation.retry:
    - is_rate_limit() — pattern matching for 429/throttle errors
    - is_fatal() — pattern matching for content filter/auth errors
    - is_transient() — pattern matching for server errors
    - parse_retry_seconds() — extraction from error text with clamping
    - should_retry() — decision logic combining all classifiers
    - get_model_fallback_queue() — env var driven model list
    - log_retry() — structured logging (no crash)
"""

from __future__ import annotations

import os
import pytest


# ── is_rate_limit ────────────────────────────────────────────────────────────


class TestIsRateLimit:
    """Rate-limit detection from exception text."""

    def test_http_429(self):
        from app.foundation.retry import is_rate_limit
        assert is_rate_limit(Exception("HTTP 429 Too Many Requests"))

    def test_rate_limit_string(self):
        from app.foundation.retry import is_rate_limit
        assert is_rate_limit(Exception("Rate limit exceeded"))

    def test_retry_after(self):
        from app.foundation.retry import is_rate_limit
        assert is_rate_limit(Exception("Please retry after 30 seconds"))

    def test_throttled(self):
        from app.foundation.retry import is_rate_limit
        assert is_rate_limit(Exception("Request was throttled"))

    def test_token_rate_limit(self):
        from app.foundation.retry import is_rate_limit
        assert is_rate_limit(Exception("Token rate limit reached"))

    def test_auth_error_not_rate_limit(self):
        from app.foundation.retry import is_rate_limit
        assert not is_rate_limit(Exception("401 Unauthorized"))

    def test_content_filter_not_rate_limit(self):
        from app.foundation.retry import is_rate_limit
        assert not is_rate_limit(Exception("content_filter triggered"))

    def test_generic_error_not_rate_limit(self):
        from app.foundation.retry import is_rate_limit
        assert not is_rate_limit(Exception("Something broke"))


# ── is_fatal ─────────────────────────────────────────────────────────────────


class TestIsFatal:
    """Fatal error detection — should never be retried."""

    def test_content_filter(self):
        from app.foundation.retry import is_fatal
        assert is_fatal(Exception("content_filter policy violation"))

    def test_content_management_policy(self):
        from app.foundation.retry import is_fatal
        assert is_fatal(Exception("Blocked by content management policy"))

    def test_unauthorized(self):
        from app.foundation.retry import is_fatal
        assert is_fatal(Exception("401 Unauthorized"))

    def test_forbidden(self):
        from app.foundation.retry import is_fatal
        assert is_fatal(Exception("403 Forbidden"))

    def test_rate_limit_not_fatal(self):
        from app.foundation.retry import is_fatal
        assert not is_fatal(Exception("429 Rate limit"))

    def test_transient_not_fatal(self):
        from app.foundation.retry import is_fatal
        assert not is_fatal(Exception("Sorry, something went wrong"))

    def test_generic_not_fatal(self):
        from app.foundation.retry import is_fatal
        assert not is_fatal(Exception("Connection timed out"))


# ── is_transient ─────────────────────────────────────────────────────────────


class TestIsTransient:
    """Transient error detection — worth retrying."""

    def test_sorry_something_went_wrong(self):
        from app.foundation.retry import is_transient
        assert is_transient(Exception("Sorry, something went wrong."))

    def test_internal_server_error(self):
        from app.foundation.retry import is_transient
        assert is_transient(Exception("500 Internal Server Error"))

    def test_502_bad_gateway(self):
        from app.foundation.retry import is_transient
        assert is_transient(Exception("502 Bad Gateway"))

    def test_503_service_unavailable(self):
        from app.foundation.retry import is_transient
        assert is_transient(Exception("503 Service Unavailable"))

    def test_504_gateway_timeout(self):
        from app.foundation.retry import is_transient
        assert is_transient(Exception("504 Gateway Timeout"))

    def test_rate_limit_not_transient(self):
        from app.foundation.retry import is_transient
        assert not is_transient(Exception("429 Rate limit"))

    def test_auth_not_transient(self):
        from app.foundation.retry import is_transient
        assert not is_transient(Exception("401 Unauthorized"))


# ── parse_retry_seconds ──────────────────────────────────────────────────────


class TestParseRetrySeconds:
    """Retry-after extraction from error text."""

    def test_retry_after_pattern(self):
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("Please retry after 30 seconds") == 30

    def test_retry_in_pattern(self):
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("retry in 10 seconds") == 10

    def test_bare_seconds_pattern(self):
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("wait 20 seconds") == 20

    def test_clamp_to_minimum(self):
        """Values below 5 are clamped to 5."""
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("retry after 1 seconds") == 5

    def test_clamp_to_maximum(self):
        """Values above 60 are clamped to 60."""
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("retry after 999 seconds") == 60

    def test_no_match_returns_default(self):
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("something broke") == 15

    def test_custom_default(self):
        from app.foundation.retry import parse_retry_seconds
        assert parse_retry_seconds("no match here", default=25) == 25


# ── should_retry ─────────────────────────────────────────────────────────────


class TestShouldRetry:
    """Retry decision logic combining all classifiers."""

    def test_fatal_never_retried(self):
        """Content filter errors are never retried."""
        from app.foundation.retry import should_retry
        retry, sleep = should_retry(Exception("content_filter"), 0, 4)
        assert retry is False
        assert sleep == 0

    def test_fatal_not_retried_even_at_attempt_0(self):
        from app.foundation.retry import should_retry
        retry, _ = should_retry(Exception("unauthorized"), 0, 10)
        assert retry is False

    def test_rate_limit_retried_with_parsed_sleep(self):
        from app.foundation.retry import should_retry
        retry, sleep = should_retry(Exception("429 retry after 30 seconds"), 0, 4)
        assert retry is True
        assert sleep == 30

    def test_rate_limit_default_sleep(self):
        """Rate limit without parseable seconds → default 15s."""
        from app.foundation.retry import should_retry
        retry, sleep = should_retry(Exception("HTTP 429"), 0, 4)
        assert retry is True
        assert sleep == 15

    def test_transient_retried_with_backoff(self):
        from app.foundation.retry import should_retry
        retry, sleep = should_retry(Exception("Sorry, something went wrong"), 0, 4)
        assert retry is True
        assert sleep == 2  # 2^0 * 2 = 2

    def test_transient_backoff_grows(self):
        from app.foundation.retry import should_retry
        _, sleep0 = should_retry(Exception("Sorry, something went wrong"), 0, 4)
        _, sleep1 = should_retry(Exception("Sorry, something went wrong"), 1, 4)
        _, sleep2 = should_retry(Exception("Sorry, something went wrong"), 2, 4)
        assert sleep0 < sleep1 < sleep2

    def test_transient_backoff_capped_at_30(self):
        from app.foundation.retry import should_retry
        _, sleep = should_retry(Exception("Sorry, something went wrong"), 10, 20)
        assert sleep <= 30

    def test_attempts_exhausted(self):
        """Last attempt (attempt == max_retries - 1) → don't retry."""
        from app.foundation.retry import should_retry
        retry, _ = should_retry(Exception("429 rate limit"), 3, 4)
        assert retry is False

    def test_unknown_error_retried(self):
        """Unknown errors are conservatively retried."""
        from app.foundation.retry import should_retry
        retry, sleep = should_retry(Exception("weird error XYZ"), 0, 4)
        assert retry is True
        assert sleep > 0


# ── get_model_fallback_queue ─────────────────────────────────────────────────


class TestModelFallbackQueue:
    """Model fallback queue from environment variables."""

    def test_default_queue(self, monkeypatch):
        """Default: just the primary model."""
        monkeypatch.setenv("LLM_MODEL", "gpt-5.2")
        monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)
        from app.foundation.retry import get_model_fallback_queue
        queue = get_model_fallback_queue()
        assert queue == ["gpt-5.2"]

    def test_with_fallback(self, monkeypatch):
        """Primary + one fallback."""
        monkeypatch.setenv("LLM_MODEL", "gpt-5.2")
        monkeypatch.setenv("LLM_FALLBACK_MODELS", "gpt-5.1")
        from app.foundation.retry import get_model_fallback_queue
        queue = get_model_fallback_queue()
        assert queue == ["gpt-5.2", "gpt-5.1"]

    def test_multiple_fallbacks(self, monkeypatch):
        """Primary + multiple comma-separated fallbacks."""
        monkeypatch.setenv("LLM_MODEL", "gpt-5.2")
        monkeypatch.setenv("LLM_FALLBACK_MODELS", "gpt-5.1, gpt-4.1")
        from app.foundation.retry import get_model_fallback_queue
        queue = get_model_fallback_queue()
        assert queue == ["gpt-5.2", "gpt-5.1", "gpt-4.1"]

    def test_empty_fallback(self, monkeypatch):
        """Empty LLM_FALLBACK_MODELS → just primary."""
        monkeypatch.setenv("LLM_MODEL", "gpt-5.2")
        monkeypatch.setenv("LLM_FALLBACK_MODELS", "")
        from app.foundation.retry import get_model_fallback_queue
        queue = get_model_fallback_queue()
        assert queue == ["gpt-5.2"]

    def test_primary_from_env(self, monkeypatch):
        """Primary comes from LLM_MODEL env var."""
        monkeypatch.setenv("LLM_MODEL", "custom-model")
        monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)
        from app.foundation.retry import get_model_fallback_queue
        queue = get_model_fallback_queue()
        assert queue[0] == "custom-model"


# ── log_retry ────────────────────────────────────────────────────────────────


class TestLogRetry:
    """log_retry() produces structured log output without crashing."""

    def test_rate_limit_log(self):
        """Rate limit retry is logged as type=rate_limit."""
        from app.foundation.retry import log_retry
        # Should not raise
        log_retry("test_agent", 0, 4, Exception("429 rate limit"), 15.0, model="gpt-5.2")

    def test_transient_log(self):
        """Transient error is logged as type=transient."""
        from app.foundation.retry import log_retry
        log_retry("delegation->NI", 1, 3, Exception("Sorry, something went wrong"), 4.0)

    def test_unknown_log(self):
        """Unknown error is logged as type=unknown."""
        from app.foundation.retry import log_retry
        log_retry("test", 0, 3, Exception("weird error"), 2.0)

    def test_long_error_truncated(self):
        """Very long error messages don't blow up the log."""
        from app.foundation.retry import log_retry
        long_msg = "x" * 10000
        log_retry("test", 0, 3, Exception(long_msg), 2.0)


# ── Integration: classify_error from errors.py still works ───────────────────


class TestErrorTaxonomyIntegration:
    """Verify the existing errors.py classify_error works with retry decisions."""

    def test_classify_then_should_retry(self):
        """classify_error produces codes; should_retry decides to retry or not."""
        from app.foundation.errors import classify_error
        from app.foundation.retry import should_retry, is_fatal

        # Content filtered → classify gives CONTENT_FILTERED → should not retry
        code, msg = classify_error(Exception("content_filter blocked"))
        assert code.value == "content_filtered"
        retry, _ = should_retry(Exception("content_filter blocked"), 0, 4)
        assert retry is False

    def test_timeout_retried(self):
        """Timeout errors should be retried (not fatal)."""
        import asyncio
        from app.foundation.retry import should_retry
        retry, _ = should_retry(asyncio.TimeoutError(), 0, 4)
        assert retry is True  # TimeoutError is not fatal, not rate-limit → retried as unknown
