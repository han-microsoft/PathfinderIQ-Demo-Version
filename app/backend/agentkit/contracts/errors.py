"""agentkit.contracts.errors — generic structured error taxonomy.

Module role:
    The domain-blind, transport-agnostic error contract: a machine-readable
    ``ErrorCode`` enum the frontend dispatches on, an exception → (code,
    message) classifier, a correlation-id generator, and an ``ERROR``
    ``StreamEvent`` builder. The returned messages are always client-safe —
    no raw exception text, internal URLs, or stack traces.

    HTTP-transport error helpers (``HttpErrorCode``, ``raise_http``) are NOT
    here — they couple to FastAPI and stay in the consumer's hosting glue.

Layer rule:
    stdlib + pydantic + ``agentkit.contracts.models`` only.
"""

from __future__ import annotations

import asyncio
import uuid
from enum import Enum
from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType


class ErrorCode(str, Enum):
    """Structured error classification for frontend-conditional rendering."""

    CONTENT_FILTERED = "content_filtered"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    PROVIDER_ERROR = "provider_error"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"


def generate_error_id() -> str:
    """Generate a 12-character lowercase hex error correlation ID."""
    return uuid.uuid4().hex[:12]


def classify_error(exc: Exception) -> tuple[ErrorCode, str]:
    """Map an exception to an ErrorCode and a sanitized, client-safe message."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."

    err_str = str(exc).lower()

    if any(p in err_str for p in ("content filter", "content_filter", "responsible ai")):
        return ErrorCode.CONTENT_FILTERED, "Response was filtered by content safety policy."

    if any(p in err_str for p in ("401 unauthorized", "403 forbidden", "authentication")):
        return ErrorCode.AUTH_ERROR, "Authentication failed. Please sign in again."

    if any(p in err_str for p in ("timed out", "timeout", "deadline exceeded")):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."

    if any(p in err_str for p in ("http 500", "http 502", "http 503", "http 504",
                                  "internal server error", "bad gateway",
                                  "service unavailable")):
        return ErrorCode.PROVIDER_ERROR, (
            "The AI service encountered an error. Please try again."
        )

    return ErrorCode.INTERNAL_ERROR, "An unexpected error occurred."


def make_error_event(
    error_code: ErrorCode,
    message: str,
    *,
    error_id: str = "",
    retry_after: int | None = None,
    tool_name: str | None = None,
) -> StreamEvent:
    """Construct a standardized ERROR StreamEvent with structured fields."""
    data: dict[str, Any] = {"error": message, "error_code": error_code.value}
    if error_id:
        data["error_id"] = error_id
    if retry_after is not None:
        data["retry_after"] = retry_after
    if tool_name:
        data["tool_name"] = tool_name
    return StreamEvent(event=StreamEventType.ERROR, data=data)


__all__ = [
    "ErrorCode",
    "generate_error_id",
    "classify_error",
    "make_error_event",
]
