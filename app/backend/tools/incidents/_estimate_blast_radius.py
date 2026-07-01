"""estimate_blast_radius — quantify incident impact + financial exposure (spoofed).

Module role:
    Spoofed "precomputed rollup" tool. In production this would run graph
    traversals (service -> SLA, service -> subscriber-count rollups) plus a
    precomputed cost function to sum affected users, SLA penalties, and
    contract value at risk. Doing that for real needs a data reshape
    (subscriber-count + contract-value properties on the graph), so this
    returns a deterministic precomputed estimate for the SYD-MEL corridor
    incident — the blast-radius / damage summary a CIO cares about.

Key collaborators:
    - tools._spoof_state.log_action — records the estimate in the action log
    - app.foundation.request_context.get_session_id — session isolation key

Dependents:
    Imported by: tools/incidents/__init__.py
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)

# Precomputed rollup for the SYD-MEL corridor fibre-cut incident. Numbers are
# consistent with the demo narrative ($75k/hour SLA exposure across the two
# enterprise VPNs). Mobile 5G services are examined and ruled out (bounded
# blast radius) — matching the `_discounted` nodes in the topology.
_AFFECTED_SERVICES = [
    {"id": "VPN-ACME-CORP", "type": "Enterprise VPN", "users": 1200,
     "sla": "SLA-ACME-GOLD", "penalty_per_hour_usd": 45000,
     "annual_contract_usd": 2600000},
    {"id": "VPN-BIGBANK", "type": "Enterprise VPN", "users": 900,
     "sla": "SLA-BIGBANK-SILVER", "penalty_per_hour_usd": 30000,
     "annual_contract_usd": 1600000},
    {"id": "BB-BUNDLE-SYD-NORTH", "type": "Broadband Bundle", "users": 9100,
     "sla": None, "penalty_per_hour_usd": 0, "annual_contract_usd": 0},
    {"id": "BB-BUNDLE-MEL-EAST", "type": "Broadband Bundle", "users": 7200,
     "sla": None, "penalty_per_hour_usd": 0, "annual_contract_usd": 0},
]
_NOT_AFFECTED = ["MOB-5G-SYD-2041", "MOB-5G-SYD-2042", "MOB-5G-MEL-3011"]


@tool
@traced_tool("estimate_blast_radius", backend="spoof")
async def estimate_blast_radius(
    incident_id: Annotated[str, Field(
        description=(
            "The transport link or incident under investigation, e.g. "
            "'LINK-SYD-MEL-FIBRE-01'."
        ),
    )],
    outage_hours: Annotated[float, Field(
        description="Projected outage duration in hours for the cost estimate.",
    )] = 4.0,
    **kwargs: Any,
) -> str:
    """Estimate the blast radius and financial exposure of an incident.

    Rolls up the affected services, subscriber counts, SLA penalties, and
    contract value at risk for the incident, and projects the cost of the
    outage. (Spoofed: returns a precomputed estimate for the corridor
    incident; production would compute this from graph + cost functions.)

    Args:
        incident_id: The link/incident under investigation.
        outage_hours: Projected outage duration for the cost projection.

    Returns:
        JSON string with the affected-user count, per-service breakdown,
        total SLA penalty/hour, contract value at risk, projected cost, and
        the services examined-but-ruled-out (bounded blast radius).
    """
    from app.foundation.request_context import get_session_id
    from tools._spoof_state import log_action

    sid = get_session_id()

    total_users = sum(s["users"] for s in _AFFECTED_SERVICES)
    penalty_per_hour = sum(s["penalty_per_hour_usd"] for s in _AFFECTED_SERVICES)
    contract_at_risk = sum(s["annual_contract_usd"] for s in _AFFECTED_SERVICES)
    hours = max(0.0, float(outage_hours))
    projected_cost = int(penalty_per_hour * hours)

    log_action(sid, "estimate_blast_radius", incident_id=incident_id,
               affected_users=total_users, penalty_per_hour=penalty_per_hour)

    logger.info(
        "tool.estimate_blast_radius.executed",
        extra={"session_id": sid, "incident_id": incident_id,
               "affected_users": total_users},
    )

    return json.dumps({
        "status": "estimated",
        "incident_id": incident_id,
        "affected_user_count": total_users,
        "affected_service_count": len(_AFFECTED_SERVICES),
        "services": _AFFECTED_SERVICES,
        "total_sla_penalty_per_hour_usd": penalty_per_hour,
        "contract_value_at_risk_usd": contract_at_risk,
        "projection": {
            "outage_hours": hours,
            "projected_cost_usd": projected_cost,
        },
        "not_affected": _NOT_AFFECTED,
        "methodology": (
            "Graph traversal of service->SLA and service->subscriber edges; "
            "SLA penalties summed from SLAPolicy.PenaltyPerHourUSD; subscriber "
            "counts from precomputed Service.CustomerCount rollups; cost "
            "projected over the estimated outage window."
        ),
    })
