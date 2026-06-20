"""Capability-discovery tool — the agent's window into the capability fabric.

``find_capabilities`` lets an agent (typically the orchestrator) discover which
agents and tools exist for a task by free-text query, instead of relying on a
hand-maintained roster in the prompt. Ports vm_agent's ``find_tools`` /
``find_capabilities`` discovery surface.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool
from app.capability import build_catalog, rank_entries

logger = logging.getLogger(__name__)


@tool(approval_mode="never_require")
@traced_tool("find_capabilities", backend="catalog")
async def find_capabilities(
    query: Annotated[
        str,
        Field(
            description=(
                "Free-text description of a task or capability you need. Returns "
                "the best-matching agents, tools, skills, and recipes from the "
                "live capability catalog (id, kind, name, summary, owning "
                "agents). Use this to discover which specialist agent to "
                "delegate to, which tool to call, or which skill/recipe to "
                "follow \u2014 instead of guessing."
            )
        ),
    ],
    kind: Annotated[
        str,
        Field(description="Optional filter: 'agent', 'tool', 'skill', or 'recipe' (empty = all)."),
    ] = "",
    **kwargs: Any,
) -> str:
    """Search the capability catalog for matching agents and tools."""
    catalog = build_catalog()
    results = rank_entries(catalog, query, kind=(kind or None), limit=12)
    return json.dumps({"query": query, "count": len(results), "results": results})
