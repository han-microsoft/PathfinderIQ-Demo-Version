"""Graph backend registry — Fabric-only.

Module role:
    Canonical metadata for the Fabric graph backend. Provides tool
    resolution and throttle status for downstream consumers.

Key collaborators:
    - agents (AgentRegistry)    — calls resolve_tool_for_backend()
    - routers/service_health.py — calls get_fabric_throttle_status()

Dependents:
    Called by: agents (AgentRegistry), routers, app.scenario._metadata
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Backend metadata registry ────────────────────────────────────────────────
# Single entry: Fabric is the only graph backend.

GRAPH_BACKENDS: dict[str, dict[str, Any]] = {
    "fabric": {
        "id": "fabric",
        "display_name": "Microsoft Fabric (GQL)",
        "description": "Fabric Graph Model with ISO GQL queries.",
        "module": "tools.graph_explorer._fabric",
        "function": "query_graph",
        "language": "gql",
        "prompt_file": "query_language/gql.md",
        "requires_env": [],
        "requires_scenario": [
            "services.fabric.workspace_id",
            "services.fabric.graph_model_id",
        ],
        "check_function": "check_connectivity",
    },
}


def get_active_backend_id() -> str:
    """Return the active graph backend ID. Always 'fabric'."""
    return "fabric"


def resolve_tool_for_backend(backend_id: str | None = None) -> tuple[str, str]:
    """Return (module_path, function_name) for the graph query tool.

    Always returns the Fabric implementation.

    Returns:
        Tuple of ('tools.graph_explorer._fabric', 'query_graph').
    """
    meta = GRAPH_BACKENDS["fabric"]
    return meta["module"], meta["function"]


def get_fabric_throttle_status() -> dict | None:
    """Return Fabric throttle gate status, or None if not configured.

    Wraps the tools-internal FabricThrottleGate.status() so routers
    and observability endpoints can read it without importing from tools/.

    Returns:
        Status dict from FabricThrottleGate, or None on any error.
    """
    try:
        from tools._fabric_throttle import get_fabric_gate
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Called from async context — can't await here (sync function).
            # Use the cached gate directly if it exists.
            from tools._fabric_throttle import _gate
            return _gate.status() if _gate else None
        return asyncio.run(get_fabric_gate()).status()
    except Exception:
        return None
