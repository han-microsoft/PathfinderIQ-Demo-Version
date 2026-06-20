"""Graph backend registry — Cosmos DB Gremlin.

Module role:
    Canonical metadata for the graph backend. Provides tool resolution and
    a (now no-op) throttle-status hook for downstream consumers.

    The Fabric graph backend was retired 2026-06-19; the graph topology now
    lives in Cosmos DB Gremlin (see ``tools/graph_explorer/_cosmos_gremlin.py``).
    The Cosmos Gremlin adapter owns its own token refresh + transient retry, so
    there is no separately-exposed throttle gate to report.

Key collaborators:
    - app.foundation.boot_validation — reads GRAPH_BACKENDS (requires_env/scenario)
    - app.routers.{health,observability} — call get_fabric_throttle_status()

Dependents:
    Re-exported via app.scenario.__init__.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Backend metadata registry ────────────────────────────────────────────────
# Single entry: Cosmos DB Gremlin is the graph backend.

GRAPH_BACKENDS: dict[str, dict[str, Any]] = {
    "cosmos_gremlin": {
        "id": "cosmos_gremlin",
        "display_name": "Azure Cosmos DB (Gremlin)",
        "description": "Cosmos DB Gremlin graph queried with Apache TinkerPop traversals.",
        "module": "tools.graph_explorer._cosmos_gremlin",
        "function": "query_graph",
        "language": "gremlin",
        "prompt_file": "query_language/gremlin.md",
        "requires_env": ["COSMOS_GREMLIN_ENDPOINT"],
        "requires_scenario": [],
        "check_function": "check_connectivity",
    },
}


def get_active_backend_id() -> str:
    """Return the active graph backend ID. Always 'cosmos_gremlin'."""
    return "cosmos_gremlin"


def resolve_tool_for_backend(backend_id: str | None = None) -> tuple[str, str]:
    """Return (module_path, function_name) for the graph query tool.

    Always returns the Cosmos Gremlin implementation.

    Returns:
        Tuple of ('tools.graph_explorer._cosmos_gremlin', 'query_graph').
    """
    meta = GRAPH_BACKENDS["cosmos_gremlin"]
    return meta["module"], meta["function"]


def get_fabric_throttle_status() -> dict | None:
    """Graph-backend throttle status — always None for the Cosmos backend.

    Retained as a stable hook for ``routers/health.py`` and
    ``routers/observability.py`` (they treat ``None`` as ``not_configured``).
    The Cosmos Gremlin adapter handles its own retry/backoff and exposes no
    separate throttle gate, so there is no status to report.
    """
    return None
