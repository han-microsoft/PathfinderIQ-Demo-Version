"""KQL datasource adaptor — Fabric Eventhouse / Azure Data Explorer (Kusto).

Owns the generic KQL transport spine so a consumer tool need only supply:
    - a ``resolve_target`` callable (query URI + database, per-request),
    - a ``credential_provider`` (Azure token credential),
    - a ``gate_provider`` (the resilience gate; semaphore + circuit breaker),
    - optionally a read-only ``validate_fn`` and a ``transform_query`` hook
      (limit injection, cache directives — all consumer-owned query text),
    - optionally a ``project`` hook applied to the raw ``{columns, rows}``.

The adaptor never inspects the query's meaning nor projects domain vocabulary
onto the result. It shapes the Kusto response into the generic
``{columns, rows}`` envelope and hands it back (optionally through the
consumer's ``project`` hook).

Optional dependency: ``azure-kusto-data`` (the ``[kusto]`` extra). Imported
lazily inside ``_get_client`` so base agentkit installs stay lean.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agentkit.contracts.envelope import error_envelope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KqlTarget:
    """Per-request KQL endpoint coordinates (resolved consumer-side)."""

    query_uri: str
    database: str


def shape_kusto_response(response: Any) -> dict[str, list]:
    """Shape a Kusto ``execute`` response into the generic envelope.

    Generic (non-domain) Kusto serialisation: primary result columns become
    ``{name, type}`` dicts; each row becomes a ``{column: value}`` dict with
    datetime-like values coerced to ISO-8601 strings. Returns
    ``{"columns": [...], "rows": [...]}`` (empty lists when there is no
    primary result).
    """
    primary = response.primary_results[0] if response.primary_results else None
    if primary is None:
        return {"columns": [], "rows": []}
    columns = [
        {"name": c.column_name, "type": c.column_type} for c in primary.columns
    ]
    rows: list[dict[str, Any]] = []
    for row in primary:
        row_dict: dict[str, Any] = {}
        for col in primary.columns:
            val = row[col.column_name]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row_dict[col.column_name] = val
        rows.append(row_dict)
    return {"columns": columns, "rows": rows}


class KqlToolAdapter:
    """Read-only KQL execution spine for a Fabric Eventhouse / Kusto cluster.

    The consumer supplies the domain-specific bits via the constructor; the
    adaptor owns client construction + caching, the resilience gate handshake,
    ``asyncio.to_thread`` execution of the synchronous Kusto SDK, generic
    response shaping, and error → envelope mapping.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], KqlTarget],
        credential_provider: Callable[[], Any],
        gate_provider: Callable[[], Awaitable[Any]],
        validate_fn: Callable[[str], str | None] | None = None,
        transform_query: Callable[[str], str] | None = None,
        not_configured_detail: str = "Datasource not configured.",
        error_detail_prefix: str = "KQL query failed",
        sanitize_error: Callable[[str], str] | None = None,
    ) -> None:
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._gate_provider = gate_provider
        self._validate_fn = validate_fn
        self._transform_query = transform_query
        self._not_configured_detail = not_configured_detail
        self._error_detail_prefix = error_detail_prefix
        self._sanitize_error = sanitize_error
        self._clients: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def circuit_state(self) -> Any:
        """Best-effort circuit state of the most recent gate (or None).

        Exposes (does not hide) the breaker state so a consumer tool can
        degrade. The gate is resolved lazily, so this returns None until the
        first ``execute`` call has fetched a gate.
        """
        gate = getattr(self, "_last_gate", None)
        return getattr(gate, "state", None) if gate is not None else None

    async def _get_client(self, query_uri: str) -> Any:
        """Get or build a cached KustoClient for ``query_uri`` (async-safe)."""
        if query_uri in self._clients:
            return self._clients[query_uri]
        async with self._lock:
            if query_uri in self._clients:
                return self._clients[query_uri]
            # Lazy import — azure-kusto-data is the [kusto] extra.
            from azure.kusto.data import (  # type: ignore[import-not-found]
                KustoClient,
                KustoConnectionStringBuilder,
            )

            cred = self._credential_provider()
            kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
                query_uri, cred
            )
            client = KustoClient(kcsb)
            self._clients[query_uri] = client
            return client

    async def execute(self, query: str, /, *, project: Callable[[dict], Any] | None = None) -> str:
        """Execute ``query`` and return the JSON wire payload.

        Pipeline: resolve target → optional read-only guard → optional query
        transform → gate acquire → ``asyncio.to_thread`` execute → shape →
        optional projection → serialise. Gate failure / SDK error map to the
        appropriate envelope; the gate is always released.
        """
        target = self._resolve_target()
        if not target.query_uri or not target.database:
            return error_envelope(self._not_configured_detail)

        if self._validate_fn is not None:
            violation = self._validate_fn(query)
            if violation:
                return error_envelope(violation)

        safe_query = self._transform_query(query) if self._transform_query else query
        logger.info("kql_adapter.execute: %s", safe_query[:200])

        gate = await self._gate_provider()
        self._last_gate = gate
        try:
            was_probe = await gate.acquire()
        except Exception as exc:  # consumer's throttle/circuit-open signal
            return error_envelope(str(exc))

        try:
            client = await self._get_client(target.query_uri)
            response = await asyncio.to_thread(client.execute, target.database, safe_query)
            shaped = shape_kusto_response(response)
            await gate.record_success()
            logger.info("kql_adapter.execute complete: %d rows", len(shaped["rows"]))
            result = project(shaped) if project is not None else shaped
            return json.dumps(result, default=str)
        except Exception as exc:
            logger.exception("kql_adapter.execute failed: %s", exc)
            err_str = str(exc).lower()
            if "429" in err_str or "throttl" in err_str:
                await gate.record_429()
            else:
                await gate.record_server_error()
            detail = (
                self._sanitize_error(str(exc))
                if self._sanitize_error is not None
                else str(exc)[:500]
            )
            return json.dumps(
                {"error": True, "detail": f"{self._error_detail_prefix}: {detail}"}
            )
        finally:
            gate.release(_was_probe=was_probe)
