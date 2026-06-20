"""Fabric IQ GraphModel (GQL over HTTP) datasource adaptor.

Generalises GridIQ's ``execute_gql`` transport: the Fabric executeQuery POST
with release-during-retry around the shared resilience gate, HTTP 429 with
``Retry-After`` + jitter, HTTP 500 ColdStartTimeout exponential backoff,
status-02000 ``nextPage`` continuation paging, and single-sentence sanitised
error dicts.

This adaptor returns the raw ``dict`` (``{"columns": [...], "data": [...]}``
on success, ``{"error": True, "detail": "..."}`` on failure) rather than a
JSON string. That is intentional: every consumer applies its own CIM /
domain projection to ``data`` before serialising, so the dict return IS the
consumer-side projection seam (binding constraint #1).

The consumer injects endpoint coordinates (a ``resolve_endpoint`` callable),
a ``token_provider``, a ``gate_provider``, and the retry/timeout budget.

Dependency: ``httpx`` (already an agentkit transport dep).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphRetryBudget:
    """Transport retry/timeout knobs for the GQL executeQuery loop."""

    http_timeout_secs: float = 100.0
    default_429_wait: int = 5
    max_429_retries: int = 5
    max_coldstart_retries: int = 5
    max_continuation_retries: int = 50
    token_stale_secs: float = 2700.0


def _parse_retry_after(response: httpx.Response, default: int) -> int:
    """Parse the ``Retry-After`` header on a 429, bounded to a sane window."""
    raw = response.headers.get("Retry-After", "")
    try:
        val = int(raw)
        return val if 0 < val <= 120 else default
    except (ValueError, TypeError):
        return default


class GraphToolAdapter:
    """Read-only Fabric GraphModel (GQL) execution spine.

    ``execute`` returns the raw ``{columns, data}`` / ``{error, detail}`` dict;
    consumers project + serialise. ``is_healthy`` performs the lightweight
    GraphModel metadata GET used by health endpoints.
    """

    def __init__(
        self,
        *,
        resolve_endpoint: Callable[[str | None], tuple[str, str, str]],
        token_provider: Callable[[], Awaitable[str]],
        gate_provider: Callable[[], Awaitable[Any]],
        budget: GraphRetryBudget | None = None,
        not_configured_detail: str = (
            "Fabric GraphModel not configured: set the workspace id "
            "and graph model id."
        ),
        metadata_url_builder: Callable[[str, str], str] | None = None,
    ) -> None:
        self._resolve_endpoint = resolve_endpoint
        self._token_provider = token_provider
        self._gate_provider = gate_provider
        self._budget = budget or GraphRetryBudget()
        self._not_configured_detail = not_configured_detail
        self._metadata_url_builder = metadata_url_builder

    async def execute(
        self, query: str, /, *, graph_model_id: str | None = None
    ) -> dict[str, Any]:
        """Run a GQL query against a Fabric GraphModel; return the raw dict."""
        _ws, _gm, url = self._resolve_endpoint(graph_model_id)
        if not url:
            return {"error": True, "detail": self._not_configured_detail}

        gate = await self._gate_provider()
        gate_state = {"held": False, "was_probe": False}
        try:
            was_probe = await gate.acquire()
            gate_state["held"] = True
            gate_state["was_probe"] = was_probe
        except Exception as exc:  # throttle / circuit-open
            return {"error": True, "detail": str(exc)}

        try:
            return await self._execute_inner(query, url, gate, gate_state=gate_state)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("graph_adapter.execute failed")
            return {"error": True, "detail": str(exc)[:500]}
        finally:
            if gate_state["held"]:
                gate.release(_was_probe=gate_state["was_probe"])
                gate_state["held"] = False

    async def _execute_inner(
        self, query: str, url: str, gate: Any, *, gate_state: dict
    ) -> dict[str, Any]:
        """Inner retry loop. Releases / re-acquires the gate around sleeps."""
        b = self._budget
        token = await self._token_provider()
        token_acquired_at = time.monotonic()

        retries_429 = 0
        retries_coldstart = 0
        retries_continuation = 0
        continuation_token: str | None = None
        aggregated_rows: list[dict[str, Any]] = []
        aggregated_columns: list[dict[str, Any]] | None = None

        max_attempts = (
            b.max_429_retries
            + b.max_coldstart_retries
            + b.max_continuation_retries
            + 2
        )

        async with httpx.AsyncClient(timeout=b.http_timeout_secs) as client:
            for _attempt in range(max_attempts):
                payload: dict[str, Any] = {"query": query}
                if continuation_token:
                    payload["continuationToken"] = continuation_token

                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

                # HTTP 429 — capacity throttled
                if response.status_code == 429:
                    retries_429 += 1
                    await gate.record_429()
                    if retries_429 > b.max_429_retries:
                        return {
                            "error": True,
                            "detail": "Fabric capacity exhausted (HTTP 429).",
                        }
                    wait = _parse_retry_after(response, b.default_429_wait) * random.uniform(0.75, 1.25)
                    logger.warning(
                        "graph_adapter.429 attempt=%d/%d wait=%.0fs",
                        retries_429, b.max_429_retries, wait,
                    )
                    await self._sleep_releasing_gate(gate, gate_state, wait)
                    continue

                # HTTP 500 ColdStartTimeout — backoff and retry
                if response.status_code == 500:
                    try:
                        body = response.json()
                    except Exception:
                        body = {}
                    if body.get("errorCode") == "ColdStartTimeout":
                        retries_coldstart += 1
                        if retries_coldstart > b.max_coldstart_retries:
                            return {
                                "error": True,
                                "detail": (
                                    "Fabric GraphModel cold start exceeded retry "
                                    "budget. Try again shortly."
                                ),
                            }
                        wait = min(
                            10 * (2 ** (retries_coldstart - 1)), 60
                        ) * random.uniform(0.75, 1.25)
                        logger.warning(
                            "graph_adapter.coldstart attempt=%d/%d wait=%.0fs",
                            retries_coldstart, b.max_coldstart_retries, wait,
                        )
                        continuation_token = None
                        await self._sleep_releasing_gate(gate, gate_state, wait)
                        if time.monotonic() - token_acquired_at > b.token_stale_secs:
                            token = await self._token_provider()
                            token_acquired_at = time.monotonic()
                        continue
                    await gate.record_server_error()
                    return {
                        "error": True,
                        "detail": f"Fabric GraphModel 500: {response.text[:300]}",
                    }

                # Other non-200
                if response.status_code != 200:
                    await gate.record_server_error()
                    return {
                        "error": True,
                        "detail": (
                            f"Fabric GraphModel HTTP {response.status_code}: "
                            f"{response.text[:300]}"
                        ),
                    }

                # 200 OK — inspect the GQL status code
                try:
                    body = response.json()
                except Exception:
                    return {
                        "error": True,
                        "detail": "Fabric GraphModel returned non-JSON payload.",
                    }
                status = body.get("status") or {}
                code = status.get("code", "")
                result = body.get("result") or {}

                if code and code != "00000" and code != "02000":
                    cause = status.get("cause") or {}
                    detail = (
                        cause.get("description")
                        or status.get("description")
                        or f"Fabric GQL error code {code}"
                    )
                    return {"error": True, "detail": f"GQL {code}: {detail[:300]}"}

                page_columns = result.get("columns") or []
                page_data = result.get("data") or []
                if aggregated_columns is None and page_columns:
                    aggregated_columns = page_columns
                aggregated_rows.extend(page_data)

                if code == "02000" and result.get("nextPage"):
                    retries_continuation += 1
                    if retries_continuation > b.max_continuation_retries:
                        return {
                            "error": True,
                            "detail": "Fabric GQL continuation retry budget exhausted.",
                        }
                    continuation_token = result["nextPage"]
                    logger.info(
                        "graph_adapter.continuation attempt=%d/%d",
                        retries_continuation, b.max_continuation_retries,
                    )
                    await self._sleep_releasing_gate(gate, gate_state, 10)
                    continue

                await gate.record_success()
                return {
                    "columns": aggregated_columns or [],
                    "data": aggregated_rows,
                }

        return {
            "error": True,
            "detail": "Fabric GQL exhausted all retry attempts.",
        }

    async def _sleep_releasing_gate(self, gate: Any, gate_state: dict, wait: float) -> None:
        """Release the gate, sleep, then re-acquire — long sleeps must not pin
        the shared semaphore (other Fabric tools would starve)."""
        try:
            gate.release(_was_probe=gate_state["was_probe"])
        finally:
            gate_state["held"] = False
            gate_state["was_probe"] = False
        await asyncio.sleep(wait)
        new_probe = await gate.acquire()
        gate_state["held"] = True
        gate_state["was_probe"] = new_probe

    async def is_healthy(self) -> bool:
        """Lightweight GraphModel metadata GET; True iff HTTP 200."""
        ws, gm, _ = self._resolve_endpoint(None)
        if not ws or not gm or self._metadata_url_builder is None:
            return False
        try:
            token = await self._token_provider()
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self._metadata_url_builder(ws, gm),
                    headers={"Authorization": f"Bearer {token}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
