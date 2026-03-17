"""Shared retry logic — rate-limit detection, backoff, and LLM model fallback.

Module role:
    Provides reusable retry primitives for LLM streaming operations.
    Used by both agent.py (orchestrator/direct chat) and delegation tool
    (specialist streaming). Centralizes rate-limit detection that was
    previously duplicated across both files.

Key collaborators:
    - app.services.llm.agent (stream_completion retry)
    - tools.delegation (specialist streaming retry)
    - app.foundation.errors (classify_error for fatal vs transient)

Dependents:
    Called by: agent.py, delegation/__init__.py
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ── Rate limit detection ─────────────────────────────────────────────────────

_RATE_LIMIT_PATTERNS = ("429", "rate limit", "retry after", "throttl", "token rate limit")

# Patterns that indicate a fatal error — never retry these
_FATAL_PATTERNS = ("content_filter", "content management policy", "unauthorized", "forbidden")


def is_rate_limit(exc: Exception) -> bool:
    """Detect rate-limit errors from exception text.

    Checks for HTTP 429, "rate limit", "retry after", "throttl", and
    "token rate limit" patterns in the lowercased exception string.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception indicates a rate-limit error.
    """
    err_str = str(exc).lower()
    return any(p in err_str for p in _RATE_LIMIT_PATTERNS)


def is_fatal(exc: Exception) -> bool:
    """Detect fatal errors that should never be retried.

    Content filter violations, auth errors — retrying these wastes time.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is fatal and should not be retried.
    """
    err_str = str(exc).lower()
    return any(p in err_str for p in _FATAL_PATTERNS)


def is_transient(exc: Exception) -> bool:
    """Detect transient server errors that may succeed on retry.

    The Azure AI Agent Service returns generic "Sorry, something went wrong"
    on transient failures. These are worth retrying.

    Args:
        exc: The exception to check.

    Returns:
        True if the exception looks transient.
    """
    err_str = str(exc).lower()
    return any(p in err_str for p in (
        "sorry, something went wrong",
        "internal server error",
        "502", "503", "504",
        "service unavailable",
        "gateway timeout",
    ))


def parse_retry_seconds(error_text: str, default: int = 15) -> int:
    """Extract retry-after seconds from error message. Clamps to [5, 60].

    Looks for patterns like "retry after 10 seconds", "retry in 10s",
    or bare "10 seconds" in the error text.

    Args:
        error_text: The lowercased error message to scan.
        default: Fallback value when no parseable seconds found.

    Returns:
        Parsed seconds clamped to [5, 60], or default if no match.
    """
    text = error_text.lower()
    match = re.search(r"retry\s*(?:after|in)\s*(\d+)", text)
    if not match:
        match = re.search(r"(\d+)\s*second", text)
    if match:
        val = int(match.group(1))
        return max(5, min(60, val))
    return default


def should_retry(exc: Exception, attempt: int, max_retries: int) -> tuple[bool, float]:
    """Determine whether to retry and how long to wait.

    Decision logic:
        1. Fatal error (content filter, auth) → never retry
        2. Rate limit → retry with parsed retry-after
        3. Transient error → retry with exponential backoff
        4. Unknown error → retry with backoff (conservative)
        5. Attempts exhausted → don't retry

    Args:
        exc: The exception that occurred.
        attempt: Current attempt number (0-based).
        max_retries: Maximum retries allowed.

    Returns:
        (should_retry, sleep_seconds). If should_retry is False,
        sleep_seconds is 0.
    """
    # Never retry fatal errors
    if is_fatal(exc):
        return False, 0

    # Attempts exhausted
    if attempt >= max_retries - 1:
        return False, 0

    # Rate limit — parse retry-after
    if is_rate_limit(exc):
        sleep = parse_retry_seconds(str(exc))
        return True, sleep

    # Transient server error — exponential backoff
    if is_transient(exc):
        sleep = min(2 ** attempt * 2, 30)  # 2s, 4s, 8s, 16s, cap 30s
        return True, sleep

    # Unknown error — conservative backoff, still retry
    sleep = min(2 ** attempt * 2, 30)
    return True, sleep


def log_retry(
    context: str,
    attempt: int,
    max_retries: int,
    exc: Exception,
    sleep_secs: float,
    model: str = "",
) -> None:
    """Structured log for retry attempts.

    Args:
        context: What's being retried (e.g. "orchestrator", "delegation->networkInvestigator")
        attempt: Current attempt number (0-based).
        max_retries: Maximum retries allowed.
        exc: The exception that triggered the retry.
        sleep_secs: How long we'll sleep before retrying.
        model: The model being used (optional).
    """
    error_type = "rate_limit" if is_rate_limit(exc) else "transient" if is_transient(exc) else "unknown"
    logger.warning(
        "retry: context=%s, attempt=%d/%d, type=%s, sleep=%.1fs, model=%s, error=%s",
        context, attempt + 1, max_retries, error_type, sleep_secs, model or "default",
        str(exc)[:200],
    )


# ── LLM model fallback queue ─────────────────────────────────────────────────


def get_model_fallback_queue() -> list[str]:
    """Return the ordered list of models to try.

    Reads primary model from AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME env var
    (the default deployment), fallbacks from LLM_FALLBACK_MODELS (comma-separated).
    In the new per-agent model design, the actual per-agent model is resolved
    in _builder.py from scenario.yaml — this queue provides the retry fallback chain.

    Returns:
        List of model deployment names, primary first.
    """
    primary = os.environ.get("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME", "gpt-5.2")
    fallback_str = os.environ.get("LLM_FALLBACK_MODELS", "")
    fallbacks = [f.strip() for f in fallback_str.split(",") if f.strip()]
    return [primary] + fallbacks
