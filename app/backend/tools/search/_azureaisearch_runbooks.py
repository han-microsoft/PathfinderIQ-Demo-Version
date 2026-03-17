"""Runbook search tool — searches operational runbooks via Azure AI Search.

Module role:
    Provides the ``search_runbooks`` ``@tool`` function that the agent calls
    when it needs standard operating procedures, diagnostic steps, escalation
    paths, or remediation guidance. Delegates to the shared ``search_index()``
    helper in ``_search.py`` which performs semantic + vector hybrid search.

Search behavior:
    - Semantic search with extractive captions
    - Vector search via VectorizableTextQuery (server-side embedding)
    - Results ranked by hybrid score, top 5 returned
    - Index name from RUNBOOKS_INDEX_NAME env var (synced from scenario.yaml)

Key collaborators:
    - ``_azureaisearch_client.py`` – shared search_index() function
    - ``app.config.settings`` – provides RUNBOOKS_INDEX_NAME

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
@traced_tool("search_runbooks", backend="azureaisearch")
async def search_runbooks(
    query: Annotated[
        str,
        Field(
            description=(
                "Search query for operational runbooks. Use when you need "
                "standard operating procedures, diagnostic steps, escalation "
                "paths, or remediation guidance. Example: 'fibre cut procedure', "
                "'optical degradation troubleshooting', 'BGP peer down escalation'."
            )
        ),
    ],
    **kwargs: Any,
) -> str:
    """Search operational runbooks for SOPs, diagnostic procedures, and escalation paths."""
    from tools.search._azureaisearch_client import search_index

    return await asyncio.to_thread(
        search_index,
        query,
        index_name=get_search_index_name("runbooks", "RUNBOOKS_INDEX_NAME", "runbooks-index"),
        semantic_config=get_semantic_config_name("runbooks", "runbooks-semantic"),
    )
