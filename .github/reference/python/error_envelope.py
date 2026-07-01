#!/usr/bin/env python3
"""error_envelope — the error-chokepoint pattern. Standalone, self-proving.

Reference exemplar (PATTERNS.md §1). Lifted + simplified from a production
agentkit where 20+ sites once open-coded `{"error": str(exc)}` and the
sanitization rule drifted per site. The fix: route every boundary error through
ONE function that caps, strips, and classifies.

What good looks like:
    - single source of truth for the error contract;
    - never leak raw exception text, internal URLs, or secrets across a boundary;
    - machine-readable code the caller/frontend can dispatch on.

Stdlib only. Run `python3 error_envelope.py` for the self-proof.
"""
from __future__ import annotations

import json
import re
import uuid
from enum import Enum
from typing import Final

_DETAIL_CAP: Final[int] = 500
_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https?://\S+")


class ErrorCode(str, Enum):
    """Structured classification — the caller renders/branches on this, not text."""

    CONTENT_FILTERED = "content_filtered"
    TOOL_TIMEOUT = "tool_timeout"
    PROVIDER_ERROR = "provider_error"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    INTERNAL_ERROR = "internal_error"


def _sanitize(detail: str) -> str:
    """Cap + URL-strip. The single rule every envelope obeys (the chokepoint)."""
    if not isinstance(detail, str):
        detail = str(detail)
    detail = _URL_PATTERN.sub("<redacted-url>", detail)
    return detail[:_DETAIL_CAP]


def generate_error_id() -> str:
    """12-char correlation id — ties a client-facing error to a server log line."""
    return uuid.uuid4().hex[:12]


def classify_error(exc: Exception) -> tuple[ErrorCode, str]:
    """Map an exception to (code, client-safe message). Never returns raw text."""
    if isinstance(exc, TimeoutError):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."
    s = str(exc).lower()
    if any(p in s for p in ("content filter", "responsible ai")):
        return ErrorCode.CONTENT_FILTERED, "Response was filtered by safety policy."
    if any(p in s for p in ("401", "403", "unauthorized", "authentication")):
        return ErrorCode.AUTH_ERROR, "Authentication failed. Please sign in again."
    if any(p in s for p in ("timed out", "timeout", "deadline exceeded")):
        return ErrorCode.TIMEOUT, "Request timed out. Please try again."
    if any(p in s for p in ("500", "502", "503", "bad gateway", "unavailable")):
        return ErrorCode.PROVIDER_ERROR, "The service encountered an error. Retry."
    return ErrorCode.INTERNAL_ERROR, "An unexpected error occurred."


def error_envelope(detail: str) -> str:
    """Canonical error envelope: `{"error": true, "detail": "<sanitized>"}`."""
    return json.dumps({"error": True, "detail": _sanitize(detail)})


def from_exception(exc: Exception) -> str:
    """Build a fully-classified, correlation-tagged, sanitized envelope."""
    code, msg = classify_error(exc)
    return json.dumps({
        "error": True,
        "error_code": code.value,
        "error_id": generate_error_id(),
        "detail": _sanitize(msg),
    })


__all__ = ["ErrorCode", "error_envelope", "from_exception", "classify_error",
           "generate_error_id"]


def _selfproof() -> None:
    # URL leak is stripped — deployment topology never crosses the boundary.
    leaked = error_envelope("connect failed: https://secret.internal.azure.com/db")
    assert "secret.internal" not in leaked, leaked
    assert "<redacted-url>" in leaked, leaked

    # Detail is capped — an SDK dumping 10kB cannot flood the client.
    assert len(json.loads(error_envelope("x" * 9000))["detail"]) == _DETAIL_CAP

    # Classification maps exceptions to safe codes, never raw text.
    code, msg = classify_error(TimeoutError("deadline exceeded at 10.0.0.1"))
    assert code is ErrorCode.TIMEOUT and "10.0.0.1" not in msg, (code, msg)

    env = json.loads(from_exception(RuntimeError("HTTP 503 service unavailable")))
    assert env["error_code"] == "provider_error"
    assert len(env["error_id"]) == 12
    assert "503" not in env["detail"]  # raw status text never surfaced

    print("error_envelope self-proof: PASS")


if __name__ == "__main__":
    _selfproof()
