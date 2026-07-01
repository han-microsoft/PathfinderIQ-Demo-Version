"""One-time observability setup — called once from the composition root.

Module role:
    Single entry-point function ``configure()`` that sets up all observability
    infrastructure in one call.  Reads ``otel_export_target`` from the
    registered settings to decide where (or whether) to export telemetry data.

    Three responsibilities, in order:
      1. **JSON structured logging** — always active, replaces ``basicConfig``
      2. **Correlation ID middleware** — always active, injects ``request_id``
      3. **OTel providers + auto-instrumentation** — only when export target
         is non-empty; otherwise noop (zero overhead)

    Supported export targets:
      - ``""`` (empty / absent) — noop exporters, JSON logs only
      - ``"console"``          — prints spans + metrics to stdout
      - ``"azure"``            — exports to Azure Monitor / Application Insights
      - ``"otlp"``             — exports to any OTLP collector (Grafana, Jaeger, etc.)

Settings seam:
    Reads ``agentkit.config.get_settings()`` (the process-wide instance
    registered by the composition root) at call time — never imports a GridIQ
    package. The generic fields it reads (``otel_export_target``,
    ``applicationinsights_connection_string``, ``otlp_endpoint``,
    ``app_version``) live on ``BaseAgentSettings``.

Service-name seam (inc6 configurable-hook pattern):
    The OTel resource service name is a consumer-supplied identity. agentkit
    defaults it to ``"agentkit-service"``; the composition root overrides it
    via :func:`set_service_name` so traces/metrics attribute to the host app.

Dependents:
    Called by: the composition root at application startup (before lifespan).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentkit.config.settings import get_settings
from agentkit.observability import _logging as _log_mod

if TYPE_CHECKING:
    # FastAPI is referenced only in type annotations (this module uses
    # ``from __future__ import annotations`` so annotations are never
    # evaluated at runtime). Keeping the import behind TYPE_CHECKING means
    # ``agentkit.observability`` imports with the lean base (stdlib + pydantic)
    # — fastapi stays gated behind the ``[fastapi]`` extra. The runtime
    # auto-instrumentation import lives lazily inside ``_wire_providers``.
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Holds references to TracerProvider and MeterProvider for graceful shutdown.
# Populated by _wire_providers() when OTel export is enabled.
_otel_providers: dict = {}

# ── Service-name seam ────────────────────────────────────────────────────────
# OTel resource ``service.name`` attribute. The composition root may override
# the generic default via ``set_service_name`` before ``configure()`` runs.
_service_name: str = "agentkit-service"


def set_service_name(name: str) -> None:
    """Register the OTel resource service name used by ``configure()``.

    Called by the composition root before ``configure()`` so traces and
    metrics attribute to the host application's identity.
    """
    global _service_name
    _service_name = name


def shutdown_observability(timeout_ms: int = 5000) -> None:
    """Gracefully shut down OTel providers — flushes buffered spans/metrics.

    Called from the FastAPI lifespan teardown handler.
    Safe to call when no providers are configured (noop mode).

    Args:
        timeout_ms: Maximum time to wait for flush in milliseconds.
    """
    for name in ("tracer", "meter"):
        provider = _otel_providers.get(name)
        if provider and hasattr(provider, "shutdown"):
            try:
                provider.shutdown()
                logger.info("OTel %s provider shut down", name)
            except Exception:
                logger.warning("OTel %s shutdown failed", name, exc_info=True)


def configure(app: FastAPI) -> None:
    """One-call observability setup.  Safe to call with any export target.

    Parameters:
        app: The FastAPI application instance.  Used to register middleware
             and auto-instrument routes.

    Side effects:
        - Replaces root logger config with JSON formatter + correlation filter
        - Adds ``CorrelationIdMiddleware`` to the ASGI middleware stack
        - When export target is non-empty: sets up OTel TracerProvider,
          MeterProvider, and auto-instruments FastAPI + httpx + logging
    """
    # Settings owns the export-target value; lower() applied at the read site
    # so the underlying field keeps the operator-friendly casing.
    settings = get_settings()
    target = (settings.otel_export_target or "").lower()

    # 1. JSON structured logging — always on, no OTel dependency
    _log_mod.configure_json_logging()

    # 2. Correlation ID middleware — always on. Uses a raw ASGI middleware
    #    instead of BaseHTTPMiddleware to avoid buffering streaming responses.
    from agentkit.observability._middleware import CorrelationIdMiddleware

    app.add_middleware(CorrelationIdMiddleware)

    # 3. OTel providers + auto-instrumentation — only if export target set
    if not target:
        logger.info(
            "Observability: export=noop (set OTEL_EXPORT_TARGET to enable)"
        )
        return  # JSON logs + correlation IDs active; no OTel export overhead

    trace_exporter, metric_exporter = _select_exporters(target)
    _wire_providers(trace_exporter, metric_exporter, app)
    logger.info("Observability: export=%s", target)


# ── Private helpers ──────────────────────────────────────────────────────────


def _select_exporters(target: str):
    """Return ``(trace_exporter, metric_exporter)`` for the given target.

    Parameters:
        target: One of ``"console"``, ``"azure"``, ``"otlp"``.

    Returns:
        Tuple of (SpanExporter, MetricExporter).

    Raises:
        ValueError: If ``target`` is not a recognised export backend, or if
            required settings (connection string, endpoint) are missing.

    Side effects:
        Lazy-imports exporter packages — they are only loaded when the
        corresponding target is selected.  This means ``azure-monitor-*``
        packages are not imported (or required to be installed) when the
        target is ``""`` or ``"console"``.
    """
    settings = get_settings()
    if target == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

        return ConsoleSpanExporter(), ConsoleMetricExporter()

    if target == "azure":
        conn = settings.applicationinsights_connection_string
        if not conn:
            raise ValueError(
                "OTEL_EXPORT_TARGET=azure requires "
                "APPLICATIONINSIGHTS_CONNECTION_STRING env var"
            )
        from azure.monitor.opentelemetry.exporter import (
            AzureMonitorTraceExporter,
            AzureMonitorMetricExporter,
        )

        return (
            AzureMonitorTraceExporter(connection_string=conn),
            AzureMonitorMetricExporter(connection_string=conn),
        )

    if target == "otlp":
        endpoint = settings.otlp_endpoint
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        return (
            OTLPSpanExporter(endpoint=endpoint),
            OTLPMetricExporter(endpoint=endpoint),
        )

    raise ValueError(
        f"Unknown OTEL_EXPORT_TARGET='{target}'. "
        f"Supported values: console, azure, otlp (or empty for noop)"
    )


def _wire_providers(trace_exporter, metric_exporter, app: FastAPI) -> None:
    """Set up OTel TracerProvider + MeterProvider + auto-instrumentation.

    Parameters:
        trace_exporter: An OTel ``SpanExporter`` implementation.
        metric_exporter: An OTel ``MetricExporter`` implementation.
        app: FastAPI app to instrument.

    Side effects:
        - Sets the global ``TracerProvider`` and ``MeterProvider``
        - Auto-instruments FastAPI routes (request spans)
        - Auto-instruments httpx requests (outbound call spans)
        - Injects ``otelTraceID`` / ``otelSpanID`` into log records
    """
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    # Resource identifies this service in traces/metrics.
    # service.name is consumer-supplied (set_service_name); APP_VERSION env var
    # is set at container build time (e.g. git SHA).
    app_version = get_settings().app_version
    resource = Resource.create(
        {SERVICE_NAME: _service_name, SERVICE_VERSION: app_version}
    )

    # Traces — BatchSpanProcessor buffers and exports in background
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tp)

    # Metrics — export every 60s
    reader = PeriodicExportingMetricReader(
        metric_exporter, export_interval_millis=60_000
    )
    mp = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(mp)

    # Store provider refs for graceful shutdown (called from the lifespan)
    _otel_providers["tracer"] = tp
    _otel_providers["meter"] = mp

    # Auto-instrument FastAPI (request spans), httpx (outbound spans),
    # and logging (inject trace_id / span_id into log records)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
