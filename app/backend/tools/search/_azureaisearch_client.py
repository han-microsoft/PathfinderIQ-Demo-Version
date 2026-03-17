"""Shared Azure AI Search query helper.

Module role:
    Provides the ``search_index()`` function used by both runbook and ticket
    search tools. Handles semantic + vector hybrid search with server-side
    vectorisation via ``VectorizableTextQuery`` (the search service generates
    embeddings from the query text, no local embedding model needed).

    Search clients are lazy-initialised and cached per index name to avoid
    re-creating connections on every tool invocation.

    Protected by a circuit breaker (``app.resilience``) that fast-fails
    when AI Search is down, returning a degraded response instead of
    blocking on unbounded SDK timeouts.

Authentication:
    - If AI_SEARCH_API_KEY is set, uses AzureKeyCredential (admin key).
    - If empty, falls back to DefaultAzureCredential (az login / managed identity).

Key collaborators:
    - ``azure.search.documents.SearchClient`` – Azure SDK search client
    - ``app.resilience.registry`` – circuit breaker for AI Search
    - ``runbooks.py``, ``tickets.py`` – call ``search_index()`` with index-specific config

Dependents:
    Called by: ``runbooks.py:search_runbooks()``, ``tickets.py:search_tickets()``
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.foundation.resilience import registry

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

AI_SEARCH_ENDPOINT = os.getenv("AI_SEARCH_ENDPOINT", "")
AI_SEARCH_API_KEY = os.getenv("AI_SEARCH_API_KEY", "")

# Circuit breaker — trips after 3 consecutive search failures,
# cooldown 60s before probing recovery. Prevents hammering a
# downed AI Search instance on every chat request.
_search_breaker = registry.get_or_create(
    "ai_search", failure_threshold=3, cooldown_secs=60
)

import threading as _threading

_search_clients: dict[str, Any] = {}
_search_lock = _threading.Lock()


def _get_search_client(index_name: str):
    """Lazy-init a SearchClient for the given index (thread-safe)."""
    if index_name not in _search_clients:
        with _search_lock:
            if index_name not in _search_clients:
                from azure.search.documents import SearchClient
                from app.foundation.credentials import get_azure_credential

                # Always use managed identity / az login — no API key fallback
                credential = get_azure_credential(require_fabric_sp=False)

                _search_clients[index_name] = SearchClient(
                    endpoint=AI_SEARCH_ENDPOINT,
                    index_name=index_name,
                    credential=credential,
                )
    return _search_clients[index_name]


def search_index(
    query: str,
    *,
    index_name: str,
    semantic_config: str,
    vector_field: str = "text_vector",
    top_k: int = 5,
) -> str:
    """Run semantic + vector hybrid search. Returns JSON string of results.

    Uses synchronous SearchClient (called via asyncio.to_thread from tools).
    """
    from azure.search.documents.models import (
        QueryCaptionType,
        QueryType,
        VectorizableTextQuery,
    )

    if not AI_SEARCH_ENDPOINT:
        return json.dumps({"error": True, "detail": "AI_SEARCH_ENDPOINT not configured."})

    # Circuit breaker fast-fail — if AI Search is known-down, return a
    # degraded response immediately instead of blocking on SDK timeout.
    # The LLM interprets the "degraded" key and responds without search results.
    if _search_breaker.is_open():
        logger.warning("search_index(%s): circuit breaker open — returning degraded", index_name)
        return json.dumps({
            "degraded": True,
            "detail": "Search temporarily unavailable — responding without knowledge base results.",
        })

    client = _get_search_client(index_name)
    logger.info("search_index(%s): %s", index_name, query[:200])

    search_params: dict[str, Any] = {
        "search_text": query,
        "top": top_k,
        "query_type": QueryType.SEMANTIC,
        "semantic_configuration_name": semantic_config,
        "query_caption": QueryCaptionType.EXTRACTIVE,
        "vector_queries": [
            VectorizableTextQuery(
                text=query,
                k_nearest_neighbors=50,
                fields=vector_field,
            ),
        ],
    }

    try:
        results = client.search(**search_params)
    except Exception as e:
        _search_breaker.record_failure()  # Track for circuit breaker
        logger.exception("search_index(%s) failed", index_name)
        return json.dumps({"error": True, "detail": f"Search failed: {type(e).__name__}: {e}"})

    formatted = []
    try:
        for doc in results:
            # Extract text from well-known fields (same priority as SDK)
            text = ""
            for field in ["chunk", "content", "text", "description", "body"]:
                if doc.get(field):
                    text = str(doc[field])
                    break
            if not text:
                parts = [
                    f"{k}: {v}" for k, v in doc.items()
                    if isinstance(v, str) and not k.startswith("@") and k != "id"
                ]
                text = " | ".join(parts)

            title = doc.get("title", "")
            source = doc.get("chunk_id", doc.get("id", ""))
            score = doc.get("@search.score", 0)

            formatted.append({
                "title": title,
                "source": source,
                "score": round(score, 3),
                "text": text[:2000],  # cap to avoid blowing context
            })
    except Exception as e:
        _search_breaker.record_failure()  # Track for circuit breaker
        logger.exception("search_index(%s) result iteration failed", index_name)
        return json.dumps({"error": True, "detail": f"Result processing failed: {e}"})

    # Search succeeded — record success so breaker stays/returns to CLOSED
    _search_breaker.record_success()
    logger.info("search_index(%s) complete: %d results", index_name, len(formatted))
    return json.dumps({"results": formatted, "count": len(formatted)}, default=str)
