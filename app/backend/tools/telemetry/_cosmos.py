"""Telemetry tools — Cosmos DB NoSQL (SQL API) against link/sensor + alert data.

Replaces the retired Fabric Eventhouse KQL backend (2026-06-19). Telemetry now
lives in Cosmos DB NoSQL containers; the agent emits Cosmos SQL (``SELECT ...
FROM c``). Execution + client caching + generic ``{columns, rows}`` shaping are
owned by the agentkit ``CosmosNoSqlToolAdapter``; this module owns the
agent-facing ``@tool`` surfaces only.

Two containers, two tools:
    - ``query_telemetry`` → ``telemetry`` container (link + sensor readings,
      discriminated by the ``kind`` field: 'link' | 'sensor').
    - ``query_alerts``    → ``alerts`` container (AlertStream events).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool
from tools._cosmos import alerts_adapter, telemetry_adapter

logger = logging.getLogger(__name__)


@tool(approval_mode="never_require")
@traced_tool("query_telemetry", backend="cosmos_nosql")
async def query_telemetry(
    query: Annotated[
        str,
        Field(
            description=(
                "Cosmos SQL query against the 'telemetry' container (link + sensor "
                "readings). Read-only SELECT only; 'SELECT TOP N' is injected if "
                "absent. Each document has a 'kind' field: 'link' or 'sensor'. "
                "Link docs (kind='link'): entityId (=LinkId), Timestamp, "
                "UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs. "
                "Sensor docs (kind='sensor'): entityId (=SensorId), Timestamp, "
                "SensorType, Value, Unit, Status. "
                "Do NOT query alerts here — use query_alerts. "
                "Example: SELECT * FROM c WHERE c.kind='link' AND "
                "c.entityId='LINK-SYD-MEL-FIBRE-01' ORDER BY c.Timestamp DESC. "
                "Returns JSON {columns, rows} on success, {error, detail} on failure."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Execute a read-only Cosmos SQL query against link/sensor telemetry."""
    return await telemetry_adapter.execute(query)


@tool(approval_mode="never_require")
@traced_tool("query_alerts", backend="cosmos_nosql")
async def query_alerts(
    query: Annotated[
        str,
        Field(
            description=(
                "Cosmos SQL query against the 'alerts' container (AlertStream) ONLY. "
                "Read-only SELECT only; 'SELECT TOP N' is injected if absent. "
                "Fields: AlertId, Timestamp, SourceNodeId, SourceNodeType, AlertType, "
                "Severity, Description, OpticalPowerDbm, BitErrorRate, CPUUtilPct, "
                "PacketLossPct. "
                "Example: SELECT * FROM c WHERE c.SourceNodeId='LINK-SYD-MEL-FIBRE-01' "
                "AND c.Severity='CRITICAL' ORDER BY c.Timestamp DESC. "
                "Returns JSON {columns, rows} on success, {error, detail} on failure."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Execute a read-only Cosmos SQL query against the alert stream."""
    return await alerts_adapter.execute(query)
