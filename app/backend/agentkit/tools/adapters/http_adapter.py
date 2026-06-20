"""Bearer-token JSON-over-HTTP datasource adaptor.

Generalises GridIQ's GridSFM tool transport: acquire a bearer token (managed
identity / workload identity), POST a JSON payload, walk the status ladder
(token error → transport error → 401/403 → other 4xx/5xx → non-JSON →
success), then project the decoded body.

The adaptor owns the httpx lifecycle and the status-ladder *order*. Every
operator-facing message is consumer-supplied via injected callbacks, and the
success projection (which fields to strip, how to serialise) stays
consumer-side (binding constraint #1). Future bearer-token JSON tools reuse
the ladder by supplying their own URL/token providers + message callbacks.

Dependency: ``httpx`` (already an agentkit transport dep).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)


class HttpToolAdapter:
    """Bearer-token JSON POST spine.

    ``post_json`` runs the full ladder and returns the consumer's wire string
    (an error envelope on any failure stage, else ``project(decoded_body)``).
    """

    def __init__(
        self,
        *,
        url_provider: Callable[[], str],
        token_provider: Callable[[], Awaitable[str]],
        on_token_error: Callable[[BaseException], str],
        on_transport_error: Callable[[str, BaseException], str],
        on_auth_error: Callable[[int, str], str],
        on_http_error: Callable[[int, str], str],
        on_decode_error: Callable[[BaseException], str],
        timeout: httpx.Timeout | float = 60.0,
    ) -> None:
        self._url_provider = url_provider
        self._token_provider = token_provider
        self._on_token_error = on_token_error
        self._on_transport_error = on_transport_error
        self._on_auth_error = on_auth_error
        self._on_http_error = on_http_error
        self._on_decode_error = on_decode_error
        self._timeout = timeout

    async def post_json(
        self,
        payload: dict[str, Any],
        *,
        project: Callable[[dict], str],
    ) -> str:
        """POST ``payload`` and return the projected wire string.

        On any failure stage, returns the consumer's corresponding error
        envelope; on success returns ``project(decoded_json_body)``.
        """
        url = self._url_provider()
        try:
            token = await self._token_provider()
        except Exception as exc:
            return self._on_token_error(exc)

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return self._on_transport_error(url, exc)

        if resp.status_code in (401, 403):
            return self._on_auth_error(resp.status_code, url)
        if resp.status_code >= 400:
            return self._on_http_error(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError as exc:
            return self._on_decode_error(exc)

        return project(data)
