"""Structured JSON logging with correlation context.

Module role:
    Replaces ``logging.basicConfig()`` with a JSON-structured output format
    via ``python-json-logger``.  Every log record becomes a single JSON object
    with ``timestamp``, ``level``, ``logger``, ``message``, and ``request_id``
    fields.  When OTel's ``LoggingInstrumentor`` is active (non-noop export),
    ``otelTraceID`` and ``otelSpanID`` are also injected automatically.

    When OTel export is disabled (noop mode), ``trace_id`` and ``span_id``
    are simply absent from the JSON — the rest of the structured output still
    works.  This means JSON logging is always on, regardless of export config.

Layer rule:
    stdlib + optional ``python-json-logger`` only. Reads the ``DEBUG`` env var
    directly (boundary read). No GridIQ, no settings import. Domain-blind.

Key collaborators:
    - ``_middleware.py`` — ``request_id_var`` provides the correlation ID
    - ``_bootstrap.py`` — calls ``configure_json_logging()`` during setup

Dependents:
    Called by: ``_bootstrap.configure()``
"""

from __future__ import annotations

import logging
import os
import sys

from agentkit.observability._middleware import request_id_var


class _CorrelationFilter(logging.Filter):
    """Inject ``request_id`` from contextvars into every log record.

    The ``request_id`` is set by ``_middleware`` at the start of each HTTP
    request.  Log records emitted outside a request context (e.g., during
    startup) get an empty string — harmless in JSON.

    Side effects:
        Mutates ``record.request_id`` on every log record that passes through.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach ``request_id`` attribute to the log record."""
        record.request_id = request_id_var.get("")  # type: ignore[attr-defined]
        return True


class _RequestIdSafeFormatter(logging.Formatter):
    """Stdlib formatter that tolerates log records without request_id fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Populate a blank request_id before delegating to the base formatter."""
        if not hasattr(record, "request_id"):
            record.request_id = ""  # type: ignore[attr-defined]
        return super().format(record)


def _configure_library_log_levels(*, debug: bool) -> None:
    """Clamp noisy third-party transport loggers to production-safe levels.

    Purpose:
        SDK request/response transport logs are useful during interactive
        debugging but overwhelm production request traces. The app keeps its
        own structured lifecycle and tool logs at INFO while demoting raw HTTP
        wire logs unless DEBUG is explicitly enabled.

    Parameters:
        debug: True when the process is running in debug mode.

    Side effects:
        Mutates logger levels for selected third-party libraries.
    """
    http_policy_logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
    http_policy_logger.setLevel(logging.INFO if debug else logging.WARNING)


def configure_json_logging() -> None:
    """Replace default logging config with JSON output + correlation filter.

    Reads the ``DEBUG`` env var to set the root log level.  Clears any
    existing handlers (including ``basicConfig``'s default ``StreamHandler``)
    and installs a single JSON-formatted ``StreamHandler`` writing to stdout.

    Side effects:
        - Clears ``logging.root.handlers``
        - Adds a ``StreamHandler`` with ``JsonFormatter``
        - Adds ``_CorrelationFilter`` to the root logger
        - Sets root level to DEBUG or INFO based on env var
    """
    # Build JSON formatter — maps Python field names to shorter JSON keys
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_CorrelationFilter())
    try:
        from pythonjsonlogger.json import JsonFormatter

        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
                rename_fields={
                    "asctime": "timestamp",
                    "levelname": "level",
                    "name": "logger",
                },
            )
        )
    except ModuleNotFoundError:
        handler.setFormatter(
            _RequestIdSafeFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s request_id=%(request_id)s"
            )
        )

    # Replace existing root handlers with our JSON handler
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addFilter(_CorrelationFilter())

    # Respect DEBUG env var — same logic as the old basicConfig block
    debug = os.getenv("DEBUG", "").lower() in ("true", "1", "yes")
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    _configure_library_log_levels(debug=debug)

    # Suppress uvicorn's built-in access logger — it writes its own format
    # (e.g., 'INFO:  127.0.0.1:49294 - "GET /api/... HTTP/1.1" 200 OK')
    # that bypasses our JSON formatter.  Request-level visibility is already
    # provided by FastAPI auto-instrumentation spans and our JSON logs.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = True
