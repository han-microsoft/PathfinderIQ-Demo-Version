"""Structured error taxonomy — classification, event construction, error IDs.

Module role:
    Centralizes error handling concerns that were previously scattered across
    agent.py, openai.py, and chat.py. Provides:
      1. ``ErrorCode`` enum — machine-readable error categories
      2. ``classify_error()`` — exception → (ErrorCode, message) mapping
      3. ``make_error_event()`` — constructs standardized ERROR StreamEvents
      4. ``generate_error_id()`` — 12-char hex correlation IDs

    The ``ErrorCode`` does NOT include ``rate_limited`` — that is handled by
    the existing ``StreamEventType.RATE_LIMITED`` event with its own retry
    semantics. Rate limiting is a temporary condition with automatic retry,
    not a terminal error.

Key collaborators:
    - ``app.models.StreamEvent``      — the event type constructed by make_error_event
    - ``app.models.StreamEventType``  — ERROR enum value
    - ``app.routers.chat``            — calls classify_error + make_error_event
    - ``app.services.llm.agent``      — calls classify_error + make_error_event
    - ``app.services.llm.openai``     — calls make_error_event (keeps isinstance chain)

Dependents:
    Called by: chat.py, agent.py, openai.py error handlers.
    Used by: Phase 1.1 LLMOps (LLMTrace.status maps to ErrorCode values).
    Used by: Phase 1.6 Guardrails (CONTENT_FILTERED for guardrail blocks).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from enum import Enum
from typing import Any

from app.foundation.models import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Structured error classification for frontend-conditional rendering.

    Each code maps to a specific UI behavior in the frontend error renderer:
      CONTENT_FILTERED → content policy warning badge
      TOOL_TIMEOUT     → tool-specific timeout with retry suggestion
      TOOL_ERROR       → tool execution failure with tool name
      PROVIDER_ERROR   → LLM provider failure (5xx, service unavailable)
      AUTH_ERROR        → re-authentication prompt
      TIMEOUT          → request timeout with retry button
      INTERNAL_ERROR   → generic error with error_id for support contact
    """

    CONTENT_FILTERED = "content_filtered"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    PROVIDER_ERROR = "provider_error"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"


def generate_error_id() -> str:
    """Generate a 12-character lowercase hex error correlation ID.

    Used for server-side log correlation. The raw exception text stays in
    the server log; only this ID reaches the client, allowing support to
    look up the full error without exposing internals.

    Returns:
        12-char hex string (e.g., ``"a1b2c3d4e5f6"``).
    """
    return uuid.uuid4().hex[:12]


def classify_error(exc: Exception) -> tuple[ErrorCode, str]:
    """Map an exception to an ErrorCode and sanitized human-readable message.

    Classification strategy (ordered from most-specific to least):
      1. isinstance checks for known exception base classes (asyncio, openai SDK)
      2. Contextual string patterns with guards against false positives
      3. Default fallback to INTERNAL_ERROR

    The returned message is always safe for client display — no raw exception
    text, no internal URLs, no stack traces.

    Args:
        exc: The exception to classify.

    Returns:
        (ErrorCode, message) — the code for frontend dispatch, the message
        for user display.
    """
    # ── 1. Type-based classification (most reliable) ─────────────────────

    # asyncio.TimeoutError — always a timeout
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."

    # ── 2. String-based classification (contextual patterns) ─────────────

    err_str = str(exc).lower()

    # Content filter / responsible AI — Azure OpenAI content safety
    if any(p in err_str for p in ("content filter", "content_filter", "responsible ai")):
        return ErrorCode.CONTENT_FILTERED, "Response was filtered by content safety policy."

    # Authentication — look for auth-related HTTP status codes WITH context
    if any(p in err_str for p in ("401 unauthorized", "403 forbidden", "authentication")):
        return ErrorCode.AUTH_ERROR, "Authentication failed. Please sign in again."

    # Timeout strings (for non-asyncio timeout exceptions)
    if any(p in err_str for p in ("timed out", "timeout", "deadline exceeded")):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."

    # Provider errors — server-side LLM failures (5xx with HTTP context)
    if any(p in err_str for p in ("http 500", "http 502", "http 503", "http 504",
                                   "internal server error", "bad gateway",
                                   "service unavailable")):
        return ErrorCode.PROVIDER_ERROR, (
            "The AI service encountered an error. Please try again."
        )

    # ── 3. Default fallback ──────────────────────────────────────────────

    return ErrorCode.INTERNAL_ERROR, "An unexpected error occurred."


def make_error_event(
    error_code: ErrorCode,
    message: str,
    *,
    error_id: str = "",
    retry_after: int | None = None,
    tool_name: str | None = None,
) -> StreamEvent:
    """Construct a standardized ERROR StreamEvent with structured fields.

    Centralizes error event construction that was previously duplicated
    across agent.py, openai.py, and chat.py. Ensures consistent field
    names and avoids typos in data dict keys.

    Args:
        error_code: Machine-readable error classification.
        message: Human-readable error text for client display.
        error_id: 12-char hex correlation ID (omitted from data if empty).
        retry_after: Seconds until retry is suggested (for timeouts).
        tool_name: Name of the failed tool (for TOOL_ERROR/TOOL_TIMEOUT).

    Returns:
        StreamEvent with event=ERROR and structured data payload.
    """
    data: dict[str, Any] = {
        "error": message,
        "error_code": error_code.value,
    }
    # Optional fields — only included when provided to keep payloads lean
    if error_id:
        data["error_id"] = error_id
    if retry_after is not None:
        data["retry_after"] = retry_after
    if tool_name:
        data["tool_name"] = tool_name

    return StreamEvent(event=StreamEventType.ERROR, data=data)
