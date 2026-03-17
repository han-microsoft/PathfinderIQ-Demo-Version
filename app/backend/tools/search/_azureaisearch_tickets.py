"""Ticket search tool — searches historical incident tickets via Azure AI Search.

Module role:
    Provides the ``search_tickets`` ``@tool`` function that the agent calls
    when it needs past precedents, resolution details, resolution times, or
    lessons learned from similar incidents. Delegates to the shared
    ``search_index()`` helper in ``_search.py``.

Search behavior:
    - Semantic search with extractive captions
    - Vector search via VectorizableTextQuery (server-side embedding)
    - Results ranked by hybrid score, top 5 returned
    - Index name from TICKETS_INDEX_NAME env var (synced from scenario.yaml)

Key collaborators:
    - ``_azureaisearch_client.py`` – shared search_index() function
    - ``app.config.settings`` – provides TICKETS_INDEX_NAME

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
@traced_tool("search_tickets", backend="azureaisearch")
async def search_tickets(
    query: Annotated[
        str,
        Field(
            description=(
                "Search query for historical incident tickets. Use when you need "
                "past precedents, resolution details, resolution times, or lessons "
                "learned from similar incidents. Example: 'SYD-MEL fibre cut 2025', "
                "'VPN-ACME-CORP outage', 'optical power degradation resolution'."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Search historical incident tickets for past precedents and resolutions."""
    from tools.search._azureaisearch_client import search_index

    return await asyncio.to_thread(
        search_index,
        query,
        index_name=get_search_index_name("tickets", "TICKETS_INDEX_NAME", "tickets-index"),
        semantic_config=get_semantic_config_name("tickets", "tickets-semantic"),
    )
