"""Infrastructure spec search — searches site and system specifications.

Module role:
    Provides the ``search_infra_specs`` ``@tool`` function that the agent
    calls when it needs amplifier site layouts, DWDM system specs, MPLS
    backup path designs, site access procedures, or physical plant
    documentation. Delegates to the shared ``search_index()`` helper.

Search behavior:
    - Semantic search with extractive captions
    - Vector search via VectorizableTextQuery (server-side embedding)
    - Results ranked by hybrid score, top 5 returned
    - Index name from INFRA_SPECS_INDEX_NAME env var (synced from scenario.yaml)

Key collaborators:
    - ``_azureaisearch_client.py`` — shared search_index() function
    - ``app.config.settings`` — provides INFRA_SPECS_INDEX_NAME

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

# Index name read from env var (set by scenario.yaml sync in _startup.py)
from tools.search._index_resolver import get_search_index_name, get_semantic_config_name


@tool(approval_mode="never_require")
@traced_tool("search_infra_specs", backend="azureaisearch")
async def search_infra_specs(
    query: Annotated[
        str,
        Field(
            description=(
                "Search query for infrastructure specifications. Use for amplifier "
                "site layouts, DWDM system specs, MPLS backup path designs, site "
                "access procedures, or physical plant documentation. Example: "
                "'AMP-SYD-MEL-03 site spec', 'MPLS backup path capacity', "
                "'Sydney-Melbourne DWDM channel plan'."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Search infrastructure specifications, site layouts, and system documentation."""
    from tools.search._azureaisearch_client import search_index

    return await asyncio.to_thread(
        search_index,
        query,
        index_name=get_search_index_name("infra_specs", "INFRA_SPECS_INDEX_NAME", "infra-specs-index"),
        semantic_config=get_semantic_config_name("infra_specs", "infra-specs-semantic"),
    )
