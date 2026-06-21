"""Config API routes — exposes runtime configuration to frontend and operators.

Module role:
    Provides ``GET /api/config`` (config subset for frontend) and
    ``GET /api/config/status`` (service connectivity summary).

Design rationale:
    The frontend needs certain config values (scenario name, feature flags)
    served at runtime so the build is environment-agnostic. All config is
    read from env vars and the active scenario's ``scenario.yaml`` — no
    ConfigResolver, no background discovery.

Key collaborators:
    - ``os.environ``        — env vars from control/.env or Container App
    - ``app.scenario``      — active scenario's YAML config
    - ``app.foundation.config.settings`` — validated settings

Dependents:
    Called by: frontend health dashboard, operator CLI
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user
from app.auth import User
from app.foundation.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
async def get_config(request: Request, user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return runtime configuration for frontend consumption.

    Reads from env vars and the active scenario's scenario.yaml.
    Filters out sensitive fields (credentials, secrets).

    Returns:
        Dict with public config fields.
    """
    from app.foundation.request_scope import get_request_scope

    scope = get_request_scope()

    # Read per-scenario agent model config
    agent_models: dict[str, str] = {}
    default_agent_model = settings.llm_model or ""
    try:
        cfg = scope.scenario_yaml
        agents_cfg = cfg.get("agents", {})
        default_agent_id = agents_cfg.get("default", "")
        for agent_id, agent_cfg in agents_cfg.items():
            if agent_id == "default" or not isinstance(agent_cfg, dict):
                continue
            agent_models[agent_id] = agent_cfg.get("model", settings.llm_model or "")
        if default_agent_id and isinstance(agents_cfg.get(default_agent_id), dict):
            default_agent_model = agents_cfg[default_agent_id].get("model", settings.llm_model or "")
    except Exception:
        pass

    return {
        "status": "ok",
        "scenario_name": scope.scenario_name or settings.scenario_name or os.getenv("DEFAULT_SCENARIO", ""),
        "llm_provider": settings.llm_provider or "",
        "llm_model": default_agent_model,
        "agent_models": agent_models,
        "ai_search_available": bool(os.getenv("AZURE_AI_SEARCH_ENDPOINT", "")),
        "cosmos_available": bool(os.getenv("COSMOS_SESSION_ENDPOINT", os.getenv("COSMOS_ENDPOINT", ""))),
    }


@router.get("/status")
async def get_config_status(request: Request, user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return service connectivity summary.

    Lightweight check — reports which services have endpoints configured,
    not whether they're actually reachable (use /api/services/health for that).

    Returns:
        Dict with per-service configuration status.
    """
    from app.foundation.request_scope import get_request_scope

    scope = get_request_scope()

    return {
        "status": "ok",
        "services": {
            "effective_graph_backend": bool(scope.graph_backend),
            "ai_search": bool(os.getenv("AI_SEARCH_ENDPOINT", "") or os.getenv("AZURE_AI_SEARCH_ENDPOINT", "")),
            "openai": bool(os.getenv("AZURE_AI_PROJECT_ENDPOINT", "") or os.getenv("AZURE_OPENAI_ENDPOINT", "")),
            "cosmos": bool(os.getenv("COSMOS_SESSION_ENDPOINT", "") or os.getenv("COSMOS_ENDPOINT", "")),
        },
    }
