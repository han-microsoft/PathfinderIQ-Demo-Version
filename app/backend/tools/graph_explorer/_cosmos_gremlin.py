"""Graph topology tool — Apache Gremlin against the Cosmos DB graph.

Replaces the retired Fabric GQL backend (2026-06-19). The network topology
ontology now lives in a Cosmos DB Gremlin graph; the agent emits TinkerPop
Gremlin traversals. Execution + token refresh + uvloop-safety + transient
retry are owned by the agentkit ``GremlinToolAdapter``; this module owns only
the agent-facing ``@tool`` surface and the projection of raw Gremlin results
into the frontend's ``{columns, data}`` envelope.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool
from tools._cosmos import gremlin_adapter

logger = logging.getLogger(__name__)


def _unwrap(value: Any) -> Any:
    """Flatten Gremlin's single-element multi-property lists to scalars."""
    if isinstance(value, list) and len(value) == 1:
        return value[0]
    return value


def _project_graph(result: list[Any]) -> dict[str, list]:
    """Shape a raw Gremlin result list into the ``{columns, data}`` envelope.

    Gremlin ``valueMap`` / ``project`` rows are dicts (often with list-valued
    properties); scalar traversals (e.g. ``values('x')``) yield bare values.
    Columns are the ordered union of keys observed across dict rows.
    """
    columns: list[dict[str, str]] = []
    seen: set[str] = set()
    data: list[dict[str, Any]] = []
    for row in result:
        if isinstance(row, dict):
            shaped: dict[str, Any] = {}
            for key, val in row.items():
                col = str(key)
                if col not in seen:
                    seen.add(col)
                    columns.append({"name": col, "type": "string"})
                shaped[col] = _unwrap(val)
            data.append(shaped)
        else:
            if "value" not in seen:
                seen.add("value")
                columns.append({"name": "value", "type": "string"})
            data.append({"value": _unwrap(row)})
    return {"columns": columns, "data": data}


@tool(approval_mode="never_require")
@traced_tool("query_graph", backend="cosmos_gremlin")
async def query_graph(
    query: Annotated[
        str,
        Field(
            description=(
                "Gremlin traversal against the network topology graph (Cosmos DB "
                "Gremlin / Apache TinkerPop). Must start with 'g.'. Read-only — "
                "write steps are blocked and '.limit(N)' is injected if absent. "
                "Vertex labels: CoreRouter, AggSwitch, BaseStation, TransportLink, "
                "Service, Sensor, MPLSPath, PhysicalConduit, AmplifierSite, "
                "BGPSession, SLAPolicy, Advisory, Depot, DutyRoster. "
                "Examples: g.V().hasLabel('CoreRouter').valueMap(true)  |  "
                "g.V('LINK-SYD-MEL-FIBRE-01').out().valueMap('id','label')  |  "
                "g.V().hasLabel('Service').has('ServiceId','VPN-ACME-CORP')"
                ".out('depends_on').valueMap(true). "
                "Returns JSON {columns, data} on success, {error, detail} on failure."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Execute a Gremlin traversal against the Cosmos DB topology graph."""
    return await gremlin_adapter.execute(query, project=_project_graph)
