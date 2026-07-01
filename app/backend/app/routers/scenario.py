"""Scenario router — metadata, topology, health, and assets.

Module role:
    Read-only scenario endpoints under /api/scenario.

Endpoints:
    GET  /api/scenario               — Scenario metadata (name, display_name, examples)
    GET  /api/scenario/topology      — Topology graph data for react-force-graph
    GET  /api/scenario/health        — Consistency checks (prompts, deploy match)
    GET  /api/scenario/agent-prompt  — Assembled agent instructions
    GET  /api/scenario/assets/*      — Scenario-owned static files

Dependents:
    Called by: frontend useScenario, useTopology, Header
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from app.auth import User
from app.foundation.config import settings
from app.deps import get_current_user
from app.scenario import get_scenario_file, get_scenario_metadata, load_scenario_yaml, load_topology

logger = logging.getLogger(__name__)

scenario_router = APIRouter(prefix="/scenario", tags=["scenario"])


# ── /api/scenario/* — Read-only metadata endpoints ───────────────────────────


@scenario_router.get("")
async def scenario_info(user: User = Depends(get_current_user)):
    """Return metadata about the active scenario (name, display_name, etc.)."""
    return get_scenario_metadata()


@scenario_router.get("/topology")
async def topology(user: User = Depends(get_current_user)):
    """Return the topology graph for the active scenario."""
    return load_topology()


@scenario_router.get("/health")
async def scenario_health(user: User = Depends(get_current_user)):
    """Validate scenario consistency — prompts, topology, index names, deploy match."""
    from app.scenario import get_scenario_dir

    scenario_dir = get_scenario_dir()
    prompts_dir = scenario_dir / "data" / "prompts" if scenario_dir else None
    prompt_files = list(prompts_dir.rglob("*.md")) if prompts_dir and prompts_dir.is_dir() else []

    control_dir = Path(__file__).resolve().parents[3] / "control"
    preamble_exists = (control_dir / "agent_preamble.md").exists()

    topo = load_topology()
    topo_nodes = topo.get("topology_nodes", topo.get("nodes", []))
    topology_available = len(topo_nodes) > 0

    scenario_yaml = load_scenario_yaml()
    scenario_yaml_valid = bool(scenario_yaml.get("name"))

    warnings: list[str] = []
    infra_config = Path(__file__).resolve().parents[3] / "graph_data" / "azure_config.env"
    deployed_scenario = ""
    if infra_config.exists():
        with open(infra_config) as f:
            for line in f:
                if line.startswith("DEFAULT_SCENARIO="):
                    deployed_scenario = line.strip().split("=", 1)[1]
                    break

    from app.foundation.request_scope import get_request_scope as _ctx_scope
    _active_scenario = _ctx_scope().scenario_name or settings.scenario_name or ""

    if deployed_scenario and _active_scenario and deployed_scenario != _active_scenario:
        warnings.append(
            f"Scenario mismatch: runtime='{_active_scenario}', "
            f"deployed='{deployed_scenario}'. Data may be inconsistent."
        )
    if not prompt_files:
        warnings.append("No prompt files found in scenario data/prompts/")
    if not preamble_exists:
        warnings.append("Generic preamble not found at control/agent_preamble.md")
    if not topology_available:
        warnings.append("No topology data available (topology.json missing or empty)")

    agents_block_valid = bool(scenario_yaml.get("agents"))
    if not agents_block_valid:
        warnings.append("scenario.yaml has no 'agents:' block")

    status = "ok" if not warnings else "warning"
    return {
        "status": status,
        "checks": {
            "scenario_name": _active_scenario,
            "deployed_scenario": deployed_scenario,
            "prompts_loaded": len(prompt_files) > 0,
            "prompt_files_found": len(prompt_files),
            "topology_available": topology_available,
            "topology_nodes": len(topo_nodes),
            "scenario_yaml_valid": scenario_yaml_valid,
            "agents_block_valid": agents_block_valid,
            "index_names": {
                "runbooks": _ctx_scope().search_indexes.get("runbooks", settings.runbooks_index_name),
                "tickets": _ctx_scope().search_indexes.get("tickets", settings.tickets_index_name),
            },
        },
        "warnings": warnings,
    }


@scenario_router.get("/agent-prompt")
async def agent_prompt(agent_id: str | None = None, user: User = Depends(get_current_user)):
    """Return the fully assembled agent system prompt."""
    from agents import registry
    return registry.get_agent_prompt_for_router(agent_id)


@scenario_router.get("/assets/{asset_path:path}")
async def scenario_asset(asset_path: str, scenario: str | None = None):
    """Serve an asset from the active scenario directory.

    This endpoint exists so scenario authors can keep presentation assets
    alongside scenario metadata instead of global frontend public folders.
    File resolution is delegated to ``get_scenario_file()`` which blocks path
    traversal outside the active scenario root.

    Access is intentionally limited to scenario-owned UI files so that making
    browser image requests public does not expose prompts, runbooks, or other
    authoring content that lives under the same scenario directory.
    """
    normalized = Path(asset_path).as_posix().lstrip("/")
    if not normalized.startswith("ui/"):
        raise HTTPException(status_code=404, detail="Scenario asset not found")
    asset_file = get_scenario_file(asset_path, scenario_name=scenario)
    if asset_file is None:
        raise HTTPException(status_code=404, detail="Scenario asset not found")
    return FileResponse(asset_file)


# ── /api/scenarios — runtime swap catalog ────────────────────────────────────
# Plural list endpoint backing the frontend scenario selector. The active
# scenario is resolved per-request from the X-Scenario-Name header (see
# app/_middleware.py); this router just enumerates the packs and reports which
# one is active for the current request.

scenarios_router = APIRouter(prefix="/scenarios", tags=["scenario"])


@scenarios_router.get("")
async def list_scenarios(user: User = Depends(get_current_user)):
    """List every available scenario pack + flag the request-active one."""
    from app.scenario._catalog import list_available_scenarios
    from app.foundation.request_scope import get_request_scope

    active = get_request_scope().scenario_name or settings.scenario_name or ""
    packs = list_available_scenarios()
    return {
        "active": active,
        "scenarios": [{**p, "active": p["name"] == active} for p in packs],
    }


@scenarios_router.post("/select")
async def select_scenario(payload: dict, request: Request, user: User = Depends(get_current_user)):
    """Persist the current user's scenario choice (per-user, no env mutation).

    Validates the requested scenario exists on disk (fresh, path-traversal
    guarded). The selection is stored per-user-OID; ``os.environ`` is never
    mutated, so one user's switch cannot bleed into another's requests.
    """
    from app.scenario import get_scenario_dir
    from app.services.preferences import get_preferences_store

    requested = str((payload or {}).get("scenario", "")).strip()
    if not requested or get_scenario_dir(requested) is None:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {requested!r}")

    get_preferences_store(request).set_scenario(user.oid, requested)
    return {"scenario": requested, "scenario_name": requested}
