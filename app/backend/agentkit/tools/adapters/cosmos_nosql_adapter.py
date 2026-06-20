"""Cosmos DB NoSQL datasource adaptor — Azure Cosmos SQL (core) API.

A generic, read-only transport spine for querying an Azure Cosmos DB NoSQL
container with the SQL query dialect. It is the Cosmos-native analogue of
``KqlToolAdapter``: where KQL targets a Kusto/Eventhouse cluster, this targets
a Cosmos SQL container and shapes the schemaless item stream into the same
generic ``{columns, rows}`` envelope so downstream renderers stay uniform.

The consumer supplies endpoint/database/container coordinates (constructor
args or a ``resolve_target`` callable), a credential provider (managed
identity / CLI — data-plane RBAC, no keys), and optional read-only
``validate_fn`` / ``transform_query`` / ``project`` hooks. The adaptor never
inspects query meaning nor projects domain vocabulary.

Optional dependency: ``azure-cosmos`` (the ``[cosmos]`` extra). Imported
lazily inside ``_get_container`` so base agentkit installs stay lean.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from agentkit.contracts.envelope import error_envelope

logger = logging.getLogger(__name__)

# Cosmos system metadata fields stripped from the generic envelope — they leak
# storage internals and never carry domain signal.
_SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


@dataclass(frozen=True)
class CosmosSqlTarget:
    """Per-request Cosmos NoSQL coordinates (resolved consumer-side)."""

    endpoint: str
    database: str
    container: str


def shape_cosmos_items(items: list[dict[str, Any]]) -> dict[str, list]:
    """Shape a Cosmos item stream into the generic ``{columns, rows}`` envelope.

    Cosmos items are schemaless dicts, so columns are derived as the ordered
    union of keys observed across the returned rows (system metadata fields
    stripped). Values are passed through; datetime-like values are coerced to
    ISO-8601 strings to match the KQL adaptor's wire shape. Returns
    ``{"columns": [...], "rows": [...]}`` (empty lists when there are no items).
    """
    columns: list[dict[str, str]] = []
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in items:
        row: dict[str, Any] = {}
        for key, val in item.items():
            if key in _SYSTEM_FIELDS:
                continue
            if key not in seen:
                seen.add(key)
                columns.append({"name": key, "type": type(val).__name__})
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row[key] = val
        rows.append(row)
    return {"columns": columns, "rows": rows}


class CosmosNoSqlToolAdapter:
    """Read-only Cosmos DB NoSQL (SQL API) execution spine.

    Owns: client/container construction + cache, ``asyncio.to_thread`` wrapping
    of the synchronous azure-cosmos SDK, generic item shaping, and error →
    envelope mapping. The consumer supplies the resolver, credential provider,
    and optional read-only guard / query transform / projection hooks.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], CosmosSqlTarget],
        credential_provider: Callable[[], Any],
        validate_fn: Callable[[str], str | None] | None = None,
        transform_query: Callable[[str], str] | None = None,
        max_item_count: int = 100,
        not_configured_detail: str = "Cosmos NoSQL endpoint not configured.",
        error_detail_prefix: str = "Cosmos query failed",
        sanitize_error: Callable[[str], str] | None = None,
    ) -> None:
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._validate_fn = validate_fn
        self._transform_query = transform_query
        self._max_item_count = max_item_count
        self._not_configured_detail = not_configured_detail
        self._error_detail_prefix = error_detail_prefix
        self._sanitize_error = sanitize_error
        self._clients: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def _get_container(self, target: CosmosSqlTarget) -> Any:
        """Get or build a cached container proxy for ``target`` (async-safe)."""
        cache_key = f"{target.endpoint}|{target.database}|{target.container}"
        if cache_key in self._clients:
            return self._clients[cache_key]
        async with self._lock:
            if cache_key in self._clients:
                return self._clients[cache_key]
            # Lazy import — azure-cosmos is the [cosmos] extra.
            from azure.cosmos import CosmosClient  # type: ignore[import-not-found]

            cred = self._credential_provider()
            client = CosmosClient(target.endpoint, credential=cred)
            container = client.get_database_client(target.database).get_container_client(
                target.container
            )
            self._clients[cache_key] = container
            return container

    async def execute(
        self, query: str, /, *, project: Callable[[dict], Any] | None = None
    ) -> str:
        """Execute a read-only Cosmos SQL ``query`` and return the JSON payload.

        Pipeline: resolve target → optional read-only guard → optional query
        transform → ``asyncio.to_thread`` query → shape → optional projection →
        serialise. SDK errors map to a sanitised error envelope.
        """
        target = self._resolve_target()
        if not target.endpoint or not target.database or not target.container:
            return error_envelope(self._not_configured_detail)

        if self._validate_fn is not None:
            violation = self._validate_fn(query)
            if violation:
                return error_envelope(violation)

        safe_query = self._transform_query(query) if self._transform_query else query
        logger.info("cosmos_nosql_adapter.execute: %s", safe_query[:200])

        try:
            container = await self._get_container(target)

            def _run_query() -> list[dict[str, Any]]:
                return list(
                    container.query_items(
                        query=safe_query,
                        enable_cross_partition_query=True,
                        max_item_count=self._max_item_count,
                    )
                )

            items = await asyncio.to_thread(_run_query)
            shaped = shape_cosmos_items(items)
            logger.info(
                "cosmos_nosql_adapter.execute complete: %d rows", len(shaped["rows"])
            )
            result = project(shaped) if project is not None else shaped
            return json.dumps(result, default=str)
        except Exception as exc:
            logger.exception("cosmos_nosql_adapter.execute failed: %s", exc)
            detail = (
                self._sanitize_error(str(exc))
                if self._sanitize_error is not None
                else str(exc)[:500]
            )
            return error_envelope(f"{self._error_detail_prefix}: {detail}")
