"""Cosmos-backed tool wiring — shared seams for the graph + telemetry tools.

This module is the consumer-side glue between PathfinderIQ's config and the
domain-blind agentkit datasource adapters. It owns the resolver callables
(per-request target coordinates), the credential provider, the read-only
guards, and the query transforms (limit injection). The adapters themselves
(``GremlinToolAdapter``, ``CosmosNoSqlToolAdapter``) live in ``agentkit`` and
never see PathfinderIQ vocabulary.

Backends (Fabric retired 2026-06-19):
    - GRAPH     → Cosmos DB Gremlin API  (agentkit ``GremlinToolAdapter``)
    - TELEMETRY → Cosmos DB NoSQL API    (agentkit ``CosmosNoSqlToolAdapter``)

Auth is managed identity in Azure / AzureCliCredential locally via
``app.foundation.credentials.get_azure_credential`` — no keys, data-plane RBAC.
"""

from __future__ import annotations

import re

from agentkit.tools.adapters import (
    CosmosNoSqlToolAdapter,
    CosmosSqlTarget,
    GremlinTarget,
    GremlinToolAdapter,
)

from app.foundation.config import settings
from app.foundation.credentials import get_azure_credential

# ── Credential seam ──────────────────────────────────────────────────────────


def _cosmos_credential():
    """Azure credential for Cosmos data-plane access (MI / CLI, no SP tier)."""
    return get_azure_credential()


# ── Gremlin (graph) seams ────────────────────────────────────────────────────

_GREMLIN_WRITE_RE = re.compile(
    r"\.(addV|addE|drop|property|addVertex|addEdge)\s*\(", re.IGNORECASE
)
_GREMLIN_LIMIT_RE = re.compile(r"\.(limit|range|sample)\s*\(", re.IGNORECASE)
_GREMLIN_AGG_TOKENS = (".count(", ".sum(", ".mean(", ".max(", ".min(", ".groupCount(")


def _resolve_gremlin_target() -> GremlinTarget:
    """Cosmos Gremlin coordinates for the adapter (resolver seam).

    Per-scenario ``data_sources.graph`` (database/graph) from the active
    RequestScope wins; empty fields fall back to the operator default
    ``settings.*``. Endpoint stays account-global (env / settings).
    """
    from app.foundation.request_scope import get_request_scope
    binding = get_request_scope().cosmos_graph_config
    return GremlinTarget(
        endpoint=settings.cosmos_gremlin_endpoint,
        database=binding.database or settings.cosmos_gremlin_database,
        graph=binding.graph or settings.cosmos_gremlin_graph,
    )


def _validate_gremlin_read_only(query: str) -> str | None:
    """Block Gremlin write steps; require a traversal starting at ``g``."""
    stripped = query.strip()
    if not stripped.startswith("g."):
        return "Gremlin traversal must start with 'g.' (read-only graph queries only)."
    match = _GREMLIN_WRITE_RE.search(query)
    if match:
        return (
            f"Write operations not allowed. Found '.{match.group(1)}()'. "
            "Use read-only traversals only."
        )
    return None


def _transform_gremlin(query: str) -> str:
    """Inject ``.limit(N)`` unless the traversal is an aggregate or already capped."""
    if any(tok in query for tok in _GREMLIN_AGG_TOKENS):
        return query
    if _GREMLIN_LIMIT_RE.search(query):
        return query
    return f"{query}.limit({settings.gremlin_max_results})"


gremlin_adapter = GremlinToolAdapter(
    resolve_target=_resolve_gremlin_target,
    credential_provider=_cosmos_credential,
    token_scope="https://cosmos.azure.com/.default",
    validate_fn=_validate_gremlin_read_only,
    transform_query=_transform_gremlin,
    not_configured_detail="Graph not configured (COSMOS_GREMLIN_ENDPOINT unset).",
    error_detail_prefix="Graph query failed",
)


# ── Cosmos NoSQL (telemetry) seams ───────────────────────────────────────────

_SQL_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|UPSERT|REPLACE|CREATE|DROP|ALTER|MERGE)\b",
    re.IGNORECASE,
)
_SQL_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_SQL_TOP_RE = re.compile(r"\bSELECT\s+TOP\s+\d+", re.IGNORECASE)
_SQL_URL_RE = re.compile(r"https?://\S+")


def _validate_cosmos_read_only(query: str) -> str | None:
    """Allow only read-only Cosmos SQL ``SELECT`` statements."""
    if not _SQL_SELECT_RE.match(query):
        return "Only read-only SELECT queries are allowed."
    match = _SQL_WRITE_RE.search(query)
    if match:
        return f"Write/DDL keyword '{match.group(1).upper()}' is not allowed."
    return None


def _transform_cosmos(query: str) -> str:
    """Inject ``SELECT TOP N`` if the query has no row cap."""
    if _SQL_TOP_RE.search(query):
        return query
    return _SQL_SELECT_RE.sub(
        f"SELECT TOP {settings.cosmos_query_max_rows}", query, count=1
    )


def _sanitize_cosmos_error(msg: str) -> str:
    """Strip endpoint URLs from Cosmos SDK error text; keep the query error."""
    return _SQL_URL_RE.sub("[endpoint]", msg)[:300]


def _resolve_telemetry_target() -> CosmosSqlTarget:
    """Cosmos NoSQL coordinates for link/sensor telemetry (resolver seam)."""
    from app.foundation.request_scope import get_request_scope
    binding = get_request_scope().cosmos_telemetry_config
    return CosmosSqlTarget(
        endpoint=settings.cosmos_telemetry_endpoint,
        database=binding.database or settings.cosmos_telemetry_database,
        container=binding.telemetry_container or settings.cosmos_telemetry_container,
    )


def _resolve_alerts_target() -> CosmosSqlTarget:
    """Cosmos NoSQL coordinates for the alert stream (resolver seam)."""
    from app.foundation.request_scope import get_request_scope
    binding = get_request_scope().cosmos_telemetry_config
    return CosmosSqlTarget(
        endpoint=settings.cosmos_telemetry_endpoint,
        database=binding.database or settings.cosmos_telemetry_database,
        container=binding.alerts_container or settings.cosmos_alerts_container,
    )


telemetry_adapter = CosmosNoSqlToolAdapter(
    resolve_target=_resolve_telemetry_target,
    credential_provider=_cosmos_credential,
    validate_fn=_validate_cosmos_read_only,
    transform_query=_transform_cosmos,
    max_item_count=settings.cosmos_query_max_rows,
    not_configured_detail="Telemetry not configured (COSMOS_TELEMETRY_ENDPOINT unset).",
    error_detail_prefix="Telemetry query failed",
    sanitize_error=_sanitize_cosmos_error,
)

alerts_adapter = CosmosNoSqlToolAdapter(
    resolve_target=_resolve_alerts_target,
    credential_provider=_cosmos_credential,
    validate_fn=_validate_cosmos_read_only,
    transform_query=_transform_cosmos,
    max_item_count=settings.cosmos_query_max_rows,
    not_configured_detail="Alerts not configured (COSMOS_TELEMETRY_ENDPOINT unset).",
    error_detail_prefix="Alert query failed",
    sanitize_error=_sanitize_cosmos_error,
)
