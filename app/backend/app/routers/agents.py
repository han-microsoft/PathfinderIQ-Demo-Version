"""Agents router — exposes agent definitions from scenario.yaml.

Module role:
    Provides a read-only endpoint for the frontend to discover which agents
    are defined in the active scenario and which is the default. Used by
    the frontend tab bar to auto-populate agent tabs.

Endpoints:
    GET /api/agents  — List all agent definitions with metadata

Key collaborators:
    - ``agents.registry.list_definitions()`` — reads scenario config
    - ``app.scenario``                              — provides the active scenario

Dependents:
    Called by: frontend tab bar component (step 3)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.auth import User

from agents import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/")
async def get_agents(user: User = Depends(get_current_user)) -> list[dict]:
    """Return metadata for all agents defined in the active scenario.

    Each entry contains: id, name, description, tools, tool_count, is_default.
    The frontend uses this to build agent tabs and display agent info.

    Returns:
        List of agent metadata dicts.
    """
    return registry.list_definitions()
