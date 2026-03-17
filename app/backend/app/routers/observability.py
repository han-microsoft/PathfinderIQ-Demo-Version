"""Observability router — SSE log streams + agent metadata endpoint.

Module role:
    Provides three read-only endpoints under ``/api/observability/``:
      - ``GET /logs/agent``   — SSE stream of agent SDK + tool log events
      - ``GET /logs/backend`` — SSE stream of backend framework log events
      - ``GET /status``       — JSON snapshot of last-run metadata + circuit breaker

    These endpoints are fully isolated from the chat and session routers.
    They consume LogBroadcaster instances and the FabricThrottleGate status()
    method.  No imports from routers.chat, routers.sessions, or any store.

Key collaborators:
    - ``app/log_broadcaster.py`` — provides SSE subscribe() generators
    - ``tools/fabric/_throttle.py`` — provides circuit breaker status()

Dependents:
    Called by: frontend ObservabilityPanel (EventSource + polling)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.auth import User

from app.foundation.log_broadcaster import (
    get_agent_broadcaster,
    get_backend_broadcaster,
    get_frontend_broadcaster,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observability", tags=["observability"])

# ── Last-run metadata — single source of truth in services/agent_run_state ────
# The agent service writes via update_last_run(); this router reads via
# get_last_run(). No duplicate dict — agent_run_state owns the state.
from app.services.agent_run_state import get_last_run as _get_last_run


async def _validate_sse_token(token: str | None) -> None:
    """Validate JWT token from EventSource query param.

    Called by SSE log stream endpoints. When AUTH_ENABLED=false, this
    is a no-op. When AUTH_ENABLED=true and token is missing/invalid,
    raises HTTPException(401).
    """
    from app.foundation.config import settings
    if not settings.auth_enabled:
        return
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    from app.auth import _validate_token
    try:
        await _validate_token(token)
    except HTTPException:
        raise


# ── SSE log stream endpoints ─────────────────────────────────────────────────


@router.get("/logs/agent")
async def stream_agent_logs(
    token: str | None = Query(None, description="JWT for EventSource auth"),
):
    """SSE stream of agent SDK + tool execution log events.

    Authenticated via query param token when AUTH_ENABLED=true.
    EventSource cannot set Authorization headers.
    """
    await _validate_sse_token(token)
    return StreamingResponse(
        get_agent_broadcaster().subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/logs/backend")
async def stream_backend_logs(
    token: str | None = Query(None, description="JWT for EventSource auth"),
):
    """SSE stream of backend framework log events (uvicorn, httpx, azure).

    Authenticated via query param token when AUTH_ENABLED=true.
    """
    await _validate_sse_token(token)
    return StreamingResponse(
        get_backend_broadcaster().subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Frontend console log endpoints ──────────────────────────────────────────


from pydantic import BaseModel  # noqa: E402 — grouped with endpoint for locality


class FrontendLogEntry(BaseModel):
    """Schema for a single browser console log entry POSTed by the frontend.

    Fields mirror the LogEntry type in the frontend ``useLogStream`` hook:
      - ts:    Timestamp string (HH:MM:SS.mmm)
      - level: Console level mapped to Python-style name (DEBUG/INFO/WARNING/ERROR)
      - name:  Source identifier (e.g., "console.log", "console.error")
      - msg:   The logged message text
    """
    ts: str
    level: str
    name: str
    msg: str


@router.post("/logs/frontend", status_code=204)
async def ingest_frontend_log(entry: FrontendLogEntry):
    """Receive a single browser console log entry and broadcast it.

    The frontend console interceptor POSTs each captured ``console.*`` call
    here.  The entry is injected into the frontend LogBroadcaster so that
    SSE subscribers on ``GET /logs/frontend`` receive it in real time.

    Parameters:
        entry: Validated log entry from the browser.

    Returns:
        HTTP 204 No Content on success.

    Side effects:
        Calls ``get_frontend_broadcaster().broadcast()`` with the entry dict.
    """
    get_frontend_broadcaster().broadcast(entry.model_dump())


@router.post("/logs/frontend/batch", status_code=204)
async def ingest_frontend_log_batch(entries: list[FrontendLogEntry]):
    """Receive a batch of browser console log entries and broadcast each.

    The frontend console interceptor buffers entries and POSTs them in
    batches (every 2s or 50 entries). Each entry is broadcast individually
    so SSE subscribers see them as separate events.

    Parameters:
        entries: List of validated log entries from the browser.

    Returns:
        HTTP 204 No Content on success.

    Side effects:
        Calls ``get_frontend_broadcaster().broadcast()`` for each entry.
    """
    broadcaster = get_frontend_broadcaster()
    for entry in entries:
        broadcaster.broadcast(entry.model_dump())


@router.get("/logs/frontend")
async def stream_frontend_logs(
    token: str | None = Query(None, description="JWT for EventSource auth"),
):
    """SSE stream of browser console log events.

    Authenticated via query param token when AUTH_ENABLED=true.
    """
    await _validate_sse_token(token)
    return StreamingResponse(
        get_frontend_broadcaster().subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Status / metadata endpoint ───────────────────────────────────────────────


@router.get("/status")
async def get_status(user: User = Depends(get_current_user)):
    """Return agent metadata snapshot + Fabric circuit breaker state.

    Returns:
        JSON dict with ``last_run`` and ``fabric`` sections.

    Design rationale:
        Uses ``try/except`` for Fabric gate access so the endpoint
        works even when Fabric tools are not configured (returns
        ``fabric: null``).
    """
    # Fabric circuit breaker status — optional (tools may not be configured)
    from app.scenario._registry import get_fabric_throttle_status
    fabric_status = get_fabric_throttle_status()

    return {
        "last_run": _get_last_run(),
        "fabric": fabric_status,
    }
