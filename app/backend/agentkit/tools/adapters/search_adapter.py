"""Azure AI Search datasource adaptor.

Generalises GridIQ's semantic + vector hybrid search spine: a per-endpoint
circuit breaker (a quota/transient outage on one search service must not
disable a healthy second), the benign free-tier semantic-quota retry
(re-run keyword + vector without the paid semantic re-ranker), lazy cached
``SearchClient`` construction, and error/degraded → envelope mapping.

The consumer supplies the credential provider and — critically — the
per-hit ``project_doc`` hook. Field selection (which text field wins, the
title/source fallbacks, the score cap) is consumer vocabulary and stays
consumer-side; the adaptor only iterates the SDK response and assembles the
generic ``{results, count}`` envelope.

Optional dependency: ``azure-search-documents`` (the ``[search]`` extra).
Imported lazily so base agentkit installs stay lean.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Callable

from agentkit.contracts.envelope import degraded_envelope, error_envelope
from agentkit.resilience import registry

logger = logging.getLogger(__name__)

# Substring Azure AI Search emits when the free-tier monthly semantic-query
# quota is exhausted. The service is otherwise healthy, so this is a benign
# degradation: retry without semantic ranking rather than tripping the breaker.
_SEMANTIC_QUOTA_MARKER = "Free Query Semantic Usage exceeded"


class SearchToolAdapter:
    """Read-only Azure AI Search execution spine (semantic + vector hybrid).

    Per-endpoint breakers are keyed on the endpoint string so independent
    search services fail independently. Construction caches one SDK client per
    ``(endpoint, index)`` pair.
    """

    def __init__(
        self,
        *,
        credential_provider: Callable[[], Any],
        default_endpoint: str = "",
        timeout_seconds: int = 15,
        breaker_failure_threshold: int = 3,
        breaker_cooldown_secs: int = 60,
        breaker_key_prefix: str = "ai_search",
        degraded_detail: str = "Search temporarily unavailable.",
        not_configured_detail: str = "AI_SEARCH_ENDPOINT not configured.",
    ) -> None:
        self._credential_provider = credential_provider
        self._default_endpoint = default_endpoint
        self._timeout = timeout_seconds
        self._breaker_failure_threshold = breaker_failure_threshold
        self._breaker_cooldown_secs = breaker_cooldown_secs
        self._breaker_key_prefix = breaker_key_prefix
        self._degraded_detail = degraded_detail
        self._not_configured_detail = not_configured_detail
        self._clients: dict[str, Any] = {}
        self._breakers: dict[str, Any] = {}
        self._client_lock = threading.Lock()
        self._breaker_lock = threading.Lock()

    def breaker_for(self, endpoint: str | None) -> Any:
        """Return the lazily-created circuit breaker for ``endpoint``."""
        key = f"{self._breaker_key_prefix}:{endpoint or 'default'}"
        breaker = self._breakers.get(key)
        if breaker is None:
            with self._breaker_lock:
                breaker = self._breakers.get(key)
                if breaker is None:
                    breaker = registry.get_or_create(
                        key,
                        failure_threshold=self._breaker_failure_threshold,
                        cooldown_secs=self._breaker_cooldown_secs,
                    )
                    self._breakers[key] = breaker
        return breaker

    def _get_client(self, index_name: str, endpoint: str | None) -> Any:
        resolved_endpoint = endpoint or self._default_endpoint
        cache_key = f"{resolved_endpoint}::{index_name}"
        if cache_key not in self._clients:
            with self._client_lock:
                if cache_key not in self._clients:
                    from azure.search.documents import (  # type: ignore[import-not-found]
                        SearchClient,
                    )

                    credential = self._credential_provider()
                    self._clients[cache_key] = SearchClient(
                        endpoint=resolved_endpoint,
                        index_name=index_name,
                        credential=credential,
                    )
        return self._clients[cache_key]

    def execute(
        self,
        query: str,
        /,
        *,
        index_name: str,
        semantic_config: str,
        project_doc: Callable[[dict], dict],
        vector_field: str = "text_vector",
        top_k: int = 5,
        endpoint: str | None = None,
    ) -> str:
        """Run hybrid search synchronously; return the JSON wire payload.

        Synchronous because the Azure Search SDK is synchronous — the consumer
        wraps this in ``asyncio.to_thread``. ``project_doc`` is applied per hit
        (consumer-side projection). Returns
        ``{"results": [...], "count": N}`` on success, a degraded envelope when
        the endpoint breaker is open, or an error envelope on failure.
        """
        resolved_endpoint = endpoint or self._default_endpoint
        if not resolved_endpoint:
            return error_envelope(self._not_configured_detail)

        breaker = self.breaker_for(resolved_endpoint)
        if breaker.is_open():
            logger.warning(
                "search_adapter(%s @ %s): circuit breaker open — returning degraded",
                index_name, resolved_endpoint,
            )
            return degraded_envelope(self._degraded_detail)

        client = self._get_client(index_name, endpoint=resolved_endpoint)
        logger.info("search_adapter(%s): %s", index_name, query[:200])

        from azure.search.documents.models import (  # type: ignore[import-not-found]
            QueryCaptionType,
            QueryType,
            VectorizableTextQuery,
        )

        def _run_search(use_semantic: bool) -> Any:
            params: dict[str, Any] = {
                "search_text": query,
                "top": top_k,
                "timeout": self._timeout,
            }
            if use_semantic:
                params["query_type"] = QueryType.SEMANTIC
                params["semantic_configuration_name"] = semantic_config
                params["query_caption"] = QueryCaptionType.EXTRACTIVE
            if vector_field:
                params["vector_queries"] = [
                    VectorizableTextQuery(
                        text=query,
                        k_nearest_neighbors=50,
                        fields=vector_field,
                    ),
                ]
            return client.search(**params)

        try:
            results = _run_search(use_semantic=True)
        except Exception as exc:
            if _SEMANTIC_QUOTA_MARKER in str(exc):
                logger.warning(
                    "search_adapter(%s): semantic quota exhausted, retrying non-semantic",
                    index_name,
                )
                try:
                    results = _run_search(use_semantic=False)
                except Exception as exc2:
                    breaker.record_failure()
                    logger.exception("search_adapter(%s) non-semantic retry failed", index_name)
                    return error_envelope("Search failed", exc=exc2)
            else:
                breaker.record_failure()
                logger.exception("search_adapter(%s) failed", index_name)
                return error_envelope("Search failed", exc=exc)

        formatted: list[dict[str, Any]] = []
        try:
            formatted = [project_doc(doc) for doc in results]
        except Exception as exc:
            if _SEMANTIC_QUOTA_MARKER in str(exc):
                logger.warning(
                    "search_adapter(%s): semantic quota exhausted during iteration, "
                    "retrying non-semantic",
                    index_name,
                )
                try:
                    results = _run_search(use_semantic=False)
                    formatted = [project_doc(doc) for doc in results]
                except Exception as exc2:
                    breaker.record_failure()
                    logger.exception("search_adapter(%s) non-semantic retry failed", index_name)
                    return error_envelope(f"Result processing failed: {exc2}")
            else:
                breaker.record_failure()
                logger.exception("search_adapter(%s) result iteration failed", index_name)
                return error_envelope(f"Result processing failed: {exc}")

        breaker.record_success()
        logger.info("search_adapter(%s) complete: %d results", index_name, len(formatted))
        return json.dumps({"results": formatted, "count": len(formatted)}, default=str)
