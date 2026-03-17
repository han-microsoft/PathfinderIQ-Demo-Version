"""Tool tracing decorator — creates OTel spans + standardised logging.

Module role:
    Provides the ``@traced_tool`` decorator for tool functions.  When applied,
    every invocation of the decorated tool automatically:

    1. Creates an OTel span named ``tool.<name>`` with attributes
       (``tool.name``, ``tool.backend``, ``tool.query_preview``)
    2. Logs ``tool.start`` (INFO) with the query preview
    3. On success: logs ``tool.complete`` (INFO) with duration + row count,
       increments ``tool.calls`` counter, records duration histogram
    4. On error: logs ``tool.error`` (ERROR), increments ``tool.errors``,
       records the exception on the span
    5. All of this is noop when ``OTEL_EXPORT_TARGET=""`` — the
       ``NoopTracer`` produces zero-cost spans that discard all data.

    The decorator wraps ``async def`` tool functions.  It does not modify
    the function signature, return value, or exception behaviour — callers
    see identical semantics with or without the decorator.

Usage (Phase 3 — not applied yet in Phase 1):
    from app.observability import traced_tool

    @traced_tool("query_graph", backend="fabric")
    @tool(approval_mode="never_require")
    async def query_graph(query: ..., **kwargs) -> str:
        ...  # function body unchanged

Key collaborators:
    - ``_metrics.py`` — counter and histogram instruments
    - ``_bootstrap.py`` — sets the global ``TracerProvider``

Dependents:
    Imported by: tool modules (via ``from app.observability import traced_tool``)
"""

from __future__ import annotations

import functools
import json
import logging
import re
import time
from typing import Any

try:
    from opentelemetry import trace
except ModuleNotFoundError:
    class _NoopSpan:
        """Fallback span that absorbs tracing calls when OTel is unavailable."""

        def __enter__(self) -> "_NoopSpan":
            """Return the span context manager instance."""
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            """Leave exceptions untouched while closing the noop span."""
            return False

        def set_attribute(self, key: str, value: Any) -> None:
            """Discard span attributes in noop mode."""
            return None

        def set_status(self, status: Any, description: str | None = None) -> None:
            """Discard span status updates in noop mode."""
            return None

        def record_exception(self, exc: Exception) -> None:
            """Discard recorded exceptions in noop mode."""
            return None

    class _NoopTracer:
        """Fallback tracer that yields noop spans."""

        def start_as_current_span(self, name: str, attributes: dict[str, Any] | None = None) -> _NoopSpan:
            """Create a noop span context manager for traced operations."""
            return _NoopSpan()

    class _NoopStatusCode:
        """Compatibility enum replacement for trace status values."""

        OK = "OK"
        ERROR = "ERROR"

    class _NoopTraceModule:
        """Small compatibility layer that mimics the subset of trace API we use."""

        StatusCode = _NoopStatusCode

        @staticmethod
        def get_tracer(name: str) -> _NoopTracer:
            """Return a noop tracer when observability dependencies are absent."""
            return _NoopTracer()

    trace = _NoopTraceModule()

from app.observability._metrics import (
    tool_call_counter,
    tool_duration_histogram,
    tool_error_counter,
)

logger = logging.getLogger(__name__)

# Pre-compiled regex for redacting sensitive patterns in tool query previews.
# Compiled once at module load — avoids per-call import + re.compile overhead.
_SENSITIVE_RE = re.compile(
    r"(Bearer\s+\S+|api[_-]?key[=:]\S+|password[=:]\S+|secret[=:]\S+)",
    re.IGNORECASE,
)


def get_tracer(name: str = __name__) -> Any:
    """Return an OTel ``Tracer``.  Returns ``NoopTracer`` when export is disabled.

    Parameters:
        name: Tracer name — typically ``__name__`` of the calling module.

    Returns:
        An OTel ``Tracer`` instance bound to the global ``TracerProvider``.
    """
    return trace.get_tracer(name)


def traced_tool(name: str, *, backend: str = ""):
    """Decorator factory for traced async tool functions.

    Parameters:
        name: Human-readable tool name (e.g., ``"query_graph"``).
              Used as the OTel span name suffix and in log ``extra`` fields.
        backend: Backend identifier (e.g., ``"fabric"``, ``"cosmos"``,
                 ``"azureaisearch"``).  Recorded as a span attribute.

    Returns:
        A decorator that wraps an ``async def`` tool function with span
        creation, structured logging, and metric recording.

    Side effects:
        - Creates an OTel span per invocation
        - Logs ``tool.start``, ``tool.complete``, ``tool.error``
        - Increments ``tool.calls`` / ``tool.errors`` counters
        - Records ``tool.duration_ms`` histogram
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer(func.__module__)

            # Extract a preview of the query/operation from the first positional
            # arg or well-known keyword args. Sanitize to avoid leaking PII or
            # secrets (e.g. Bearer tokens in query strings) into trace backends.
            query_preview = str(
                args[0]
                if args
                else kwargs.get("query", kwargs.get("operation", ""))
            )[:200]
            # Redact common sensitive patterns before shipping to trace backend
            query_preview = _SENSITIVE_RE.sub("[REDACTED]", query_preview)

            with tracer.start_as_current_span(
                f"tool.{name}",
                attributes={
                    "tool.name": name,
                    "tool.backend": backend,
                    "tool.query_preview": query_preview,
                },
            ) as span:
                t0 = time.monotonic()
                logger.info(
                    "tool.start",
                    extra={
                        "tool": name,
                        "backend": backend,
                        "query_preview": query_preview,
                    },
                )
                try:
                    result = await func(*args, **kwargs)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)

                    # Best-effort row count extraction from JSON result
                    row_count = _extract_row_count(result)

                    span.set_attribute("tool.duration_ms", elapsed_ms)
                    span.set_attribute("tool.row_count", row_count)
                    span.set_status(trace.StatusCode.OK)

                    logger.info(
                        "tool.complete",
                        extra={
                            "tool": name,
                            "duration_ms": elapsed_ms,
                            "row_count": row_count,
                        },
                    )

                    # Metrics (noop when no exporter configured)
                    tool_call_counter.add(1, {"tool.name": name})
                    tool_duration_histogram.record(
                        elapsed_ms, {"tool.name": name}
                    )

                    return result

                except Exception as exc:
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    span.set_status(trace.StatusCode.ERROR, str(exc))
                    span.record_exception(exc)

                    logger.error(
                        "tool.error",
                        extra={
                            "tool": name,
                            "duration_ms": elapsed_ms,
                            "error": str(exc),
                        },
                    )

                    tool_error_counter.add(1, {"tool.name": name})
                    raise

        return wrapper

    return decorator


def _extract_row_count(result: str) -> int:
    """Best-effort extraction of row count from a tool's JSON result string.

    Looks for common keys (``data``, ``rows``, ``count``, ``results``) in the
    parsed JSON and returns the list length or integer value.  Returns ``-1``
    if the result cannot be parsed or none of the keys are found.

    Parameters:
        result: Raw JSON string returned by the tool function.

    Returns:
        Number of result rows, or ``-1`` if unknown.
    """
    try:
        parsed = json.loads(result)
        if "data" in parsed and isinstance(parsed["data"], list):
            return len(parsed["data"])
        if "rows" in parsed and isinstance(parsed["rows"], list):
            return len(parsed["rows"])
        if "count" in parsed:
            return int(parsed["count"])
        if "results" in parsed and isinstance(parsed["results"], list):
            return len(parsed["results"])
    except Exception:
        pass
    return -1
