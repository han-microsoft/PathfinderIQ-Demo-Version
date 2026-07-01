"""Gremlin datasource adaptor — Cosmos DB Gremlin (Apache TinkerPop).

Generalises GridIQ's Gremlin transport spine: a token-refreshing cached
client (Cosmos access tokens expire ~hourly), a one-shot transient retry on
auth/transport failures, and the uvloop-safe execution shim (gremlin-python
spins its own asyncio loop, which must run on a worker thread with a fresh
standard loop to avoid "loop already running" under uvicorn/uvloop).

The consumer supplies endpoint/database/graph coordinates (constructor args
or a ``resolve_target`` callable), a credential provider, and optional
read-only ``validate_fn`` / ``transform_query`` / ``project`` hooks. The
adaptor never inspects query meaning nor projects domain vocabulary.

Optional dependency: ``gremlinpython`` (the ``[gremlin]`` extra). Imported
lazily so base agentkit installs stay lean.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from agentkit.contracts.envelope import error_envelope

logger = logging.getLogger(__name__)

# Recreate the client when the cached Cosmos token has fewer than this many
# seconds of life remaining. Cosmos tokens last ~1h; 5 min headroom prevents a
# query racing with an in-flight expiry.
_TOKEN_REFRESH_MARGIN_SECONDS = 300

# Transient failure markers that justify rebuilding the client + retrying once.
_AUTH_MARKERS = (
    "401", "403", "unauthorized", "unauthori", "forbidden",
    "token", "expired", "authentication",
)
_TRANSPORT_MARKERS = (
    "connection was already closed",
    "connection is closed",
    "connection reset",
    "websocket",
    "transport",
    "broken pipe",
    "eof",
)


@dataclass(frozen=True)
class GremlinTarget:
    """Cosmos Gremlin endpoint coordinates."""

    endpoint: str
    database: str
    graph: str


class GremlinToolAdapter:
    """Read-only Gremlin execution spine for a Cosmos DB graph.

    Owns: token-refreshing client cache, uvloop-safe submit, transient
    one-shot retry, generic JSON serialisation, error → envelope mapping.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], GremlinTarget],
        credential_provider: Callable[[], Any],
        token_scope: str = "https://cosmos.azure.com/.default",
        validate_fn: Callable[[str], str | None] | None = None,
        transform_query: Callable[[str], str] | None = None,
        not_configured_detail: str = "Gremlin endpoint not configured.",
        error_detail_prefix: str = "Gremlin query failed",
        token_refresh_margin_seconds: int = _TOKEN_REFRESH_MARGIN_SECONDS,
    ) -> None:
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._token_scope = token_scope
        self._validate_fn = validate_fn
        self._transform_query = transform_query
        self._not_configured_detail = not_configured_detail
        self._error_detail_prefix = error_detail_prefix
        self._refresh_margin = token_refresh_margin_seconds
        self._client: Any = None
        self._token_expires_on: float = 0.0
        self._lock = asyncio.Lock()

    async def _build_client(self, target: GremlinTarget) -> tuple[Any, float]:
        """Build a fresh gremlin-python Client + its token expiry epoch."""
        from gremlin_python.driver import (  # type: ignore[import-not-found]
            client as gremlin_client,
            serializer,
        )

        cred = self._credential_provider()
        token_obj = await asyncio.to_thread(cred.get_token, self._token_scope)
        new_client = gremlin_client.Client(
            url=target.endpoint,
            traversal_source="g",
            username=f"/dbs/{target.database}/colls/{target.graph}",
            password=token_obj.token,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )
        return new_client, float(token_obj.expires_on)

    async def _get_client(self, target: GremlinTarget, *, force_refresh: bool = False) -> Any:
        """Get or rebuild a cached client backed by a non-expired token."""
        if not force_refresh and self._client is not None:
            if (self._token_expires_on - time.time()) > self._refresh_margin:
                return self._client

        async with self._lock:
            if not force_refresh and self._client is not None:
                if (self._token_expires_on - time.time()) > self._refresh_margin:
                    return self._client

            if self._client is not None:
                try:
                    await asyncio.to_thread(self._client.close)
                except Exception as close_exc:
                    logger.warning("gremlin_adapter.client_close_failed: %s", close_exc)
                self._client = None

            new_client, expires_on = await self._build_client(target)
            self._client = new_client
            self._token_expires_on = expires_on
            logger.info(
                "gremlin_adapter.client_created: endpoint=%s db=%s graph=%s token_ttl_s=%d",
                target.endpoint, target.database, target.graph,
                int(max(0.0, expires_on - time.time())),
            )
            return self._client

    async def execute(self, query: str, /, *, project: Callable[[Any], Any] | None = None) -> str:
        """Execute ``query`` and return the JSON wire payload (a bare list).

        Optional read-only guard + query transform run consumer-side via the
        injected hooks. On success returns ``json.dumps(result, default=str)``
        (optionally through ``project``); on failure an error envelope.
        """
        target = self._resolve_target()
        if not target.endpoint:
            return error_envelope(self._not_configured_detail)

        if self._validate_fn is not None:
            violation = self._validate_fn(query)
            if violation:
                return error_envelope(violation)

        safe_query = self._transform_query(query) if self._transform_query else query
        logger.info("gremlin_adapter.execute: %s", safe_query[:200])

        auth_retry_attempted = False
        while True:
            try:
                client = await self._get_client(target)

                def _run_query() -> Any:
                    """Run the traversal in a fresh loop on a worker thread."""
                    import asyncio as _aio

                    loop = _aio.new_event_loop()
                    try:
                        _aio.set_event_loop(loop)
                        return client.submit(safe_query).all().result()
                    finally:
                        loop.close()

                result = await asyncio.to_thread(_run_query)
                logger.info("gremlin_adapter.execute complete: %d results", len(result))
                shaped = project(result) if project is not None else result
                return json.dumps(shaped, default=str)

            except Exception as exc:
                err_text = str(exc).lower()
                looks_transient = (
                    not auth_retry_attempted
                    and any(k in err_text for k in _AUTH_MARKERS + _TRANSPORT_MARKERS)
                )
                if looks_transient:
                    auth_retry_attempted = True
                    logger.warning(
                        "gremlin_adapter.transient_failure_refreshing_client: %s",
                        str(exc)[:200],
                    )
                    try:
                        await self._get_client(target, force_refresh=True)
                    except Exception as refresh_exc:
                        logger.exception(
                            "gremlin_adapter.client_refresh_failed: %s", refresh_exc
                        )
                    continue

                logger.exception("gremlin_adapter.execute failed: %s", exc)
                return error_envelope(f"{self._error_detail_prefix}: {str(exc)[:500]}")
