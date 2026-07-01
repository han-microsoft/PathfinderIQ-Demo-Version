"""agentkit datasource adaptors — public surface.

Each adaptor owns a generic read-only transport spine (client construction +
cache, resilience gate / circuit breaker, execution, raw shaping, error →
envelope). Consumers supply the query text, input sanitisation, read-only
guard, per-request target/credential resolver, and the domain projection of
the raw result (the projection is never baked into the adaptor — binding
constraint #1).

Backend SDKs are optional pip extras (``[kusto]``, ``[gremlin]``,
``[search]``) imported lazily inside each adaptor; ``graph`` and ``http`` use
``httpx`` only.
"""

from __future__ import annotations

from agentkit.tools.adapters._protocols import DataSourceAdapter, ResilienceGate
from agentkit.tools.adapters.cosmos_nosql_adapter import (
    CosmosNoSqlToolAdapter,
    CosmosSqlTarget,
    shape_cosmos_items,
)
from agentkit.tools.adapters.graph_adapter import GraphRetryBudget, GraphToolAdapter
from agentkit.tools.adapters.http_adapter import HttpToolAdapter
from agentkit.tools.adapters.kql_adapter import (
    KqlTarget,
    KqlToolAdapter,
    shape_kusto_response,
)

__all__ = [
    "DataSourceAdapter",
    "ResilienceGate",
    "KqlToolAdapter",
    "KqlTarget",
    "shape_kusto_response",
    "CosmosNoSqlToolAdapter",
    "CosmosSqlTarget",
    "shape_cosmos_items",
    "GremlinToolAdapter",
    "GremlinTarget",
    "SearchToolAdapter",
    "GraphToolAdapter",
    "GraphRetryBudget",
    "HttpToolAdapter",
]


def __getattr__(name: str):  # PEP 562 — lazy import of SDK-extra adaptors.
    """Lazily import adaptors whose modules import optional SDK names.

    ``gremlin_adapter`` / ``search_adapter`` only import their SDKs lazily too,
    so this is belt-and-braces: a bare ``from agentkit.tools.adapters import
    GremlinToolAdapter`` stays cheap and never imports the others' SDKs.
    """
    if name in ("GremlinToolAdapter", "GremlinTarget"):
        from agentkit.tools.adapters.gremlin_adapter import (
            GremlinTarget,
            GremlinToolAdapter,
        )

        return {"GremlinToolAdapter": GremlinToolAdapter, "GremlinTarget": GremlinTarget}[name]
    if name == "SearchToolAdapter":
        from agentkit.tools.adapters.search_adapter import SearchToolAdapter

        return SearchToolAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
