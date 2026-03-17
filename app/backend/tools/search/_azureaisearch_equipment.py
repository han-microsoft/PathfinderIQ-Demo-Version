"""Equipment search — searches equipment manifests and field guides.

Module role:
    Provides the ``search_equipment`` ``@tool`` function that the agent calls
    when it needs depot inventories, OTDR operating guides, splicer specs,
    or equipment availability. Delegates to the shared ``search_index()``
    helper in ``_azureaisearch_client.py``.

Search behavior:
    - Semantic search with extractive captions
    - Vector search via VectorizableTextQuery (server-side embedding)
    - Results ranked by hybrid score, top 5 returned
    - Index name from EQUIPMENT_INDEX_NAME env var (synced from scenario.yaml)

Key collaborators:
    - ``_azureaisearch_client.py`` — shared search_index() function
    - ``app.config.settings`` — provides EQUIPMENT_INDEX_NAME

Dependents:
    Imported by: ``tools/search/__init__.py``
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

from tools.search._index_resolver import get_search_index_name, get_semantic_config_name


@tool(approval_mode="never_require")
@traced_tool("search_equipment", backend="azureaisearch")
async def search_equipment(
    query: Annotated[
        str,
        Field(
            description=(
                "Search query for equipment manifests and field guides. Use when "
                "you need depot inventories, OTDR operating guides, splicer specs, "
                "or equipment availability. Example: 'Campbelltown depot OTDR', "
                "'splicer Fujikura specs', 'available OTDR nearest Goulburn'."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Search equipment manifests and operating guides at depot locations."""
    from tools.search._azureaisearch_client import search_index

    return await asyncio.to_thread(
        search_index,
        query,
        index_name=get_search_index_name("equipment", "EQUIPMENT_INDEX_NAME", "equipment-index"),
        semantic_config=get_semantic_config_name("equipment", "equipment-semantic"),
    )
