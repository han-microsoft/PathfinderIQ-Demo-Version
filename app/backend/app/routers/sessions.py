"""Session CRUD router — manages conversation sessions.

Module role:
    Implements the session lifecycle endpoints defined in API_CONTRACT.md.
    Sessions are the top-level organisational unit for conversations.
    Each session contains an ordered list of messages.

    Includes save/load support for persisting conversations to the scenario's
    ``saved_conversations/`` folder as JSON files.

Endpoints:
    POST   /api/sessions              — Create a new session
    GET    /api/sessions              — List all sessions (summaries only)
    GET    /api/sessions/{id}         — Get a session with full message history
    PATCH  /api/sessions/{id}         — Rename a session
    DELETE /api/sessions/{id}         — Delete a session
    POST   /api/sessions/{id}/save    — Save a session to disk
    POST   /api/sessions/load-saved   — Load all saved conversations into the store
    POST   /api/sessions/reset-defaults — Delete + re-clone demo conversations for user

Key collaborators:
    - ``app.services.session_store.SessionStore`` – persistence layer (in-memory or HTTP)
    - ``app.scenario``                          – resolves saved_conversations path
    - ``app.config.settings`` – reads ``scenario_name`` to tag new sessions

Dependents:
    Called by: frontend ``sessionStore.ts`` (Zustand store)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.deps import get_store, get_current_user, User
from app.foundation.models import (
    CreateSessionRequest,
    Session,
    SessionSummary,
    UpdateSessionRequest,
)
from app.services.session_store import SessionStore
from app.foundation.session_broadcaster import remove_session_broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── Delegation SSE stream ────────────────────────────────────────────────────


@router.get("/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    token: str | None = Query(None, description="JWT for EventSource auth"),
    store: SessionStore = Depends(get_store),
):
    """SSE stream of delegation events — authenticated via query param.

    EventSource cannot set Authorization headers, so the JWT is passed
    as a query parameter. Validated once on connection open.
    When AUTH_ENABLED=false, token param is ignored.

    The Ed25519 dev-sign side-channel is also honoured: if the signed-request
    middleware verified this request it attached a principal to the ASGI scope,
    so headless probes (and the regression bench) can observe the delegation /
    sub-agent tool-call stream without an interactive Entra login.
    """
    from app.foundation.config import settings

    if settings.auth_enabled:
        devsign_principal = request.scope.get("devauth_user")
        if isinstance(devsign_principal, User):
            user = devsign_principal
        elif token:
            from app.auth import _validate_token
            try:
                claims = await _validate_token(token)
            except HTTPException:
                raise
            user = User(
                oid=claims.get("oid", ""),
                email=claims.get("preferred_username", ""),
                name=claims.get("name", ""),
            )
        else:
            raise HTTPException(status_code=401, detail="Token required")
        session = await store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        _check_ownership(session, user)

    from app.foundation.session_broadcaster import get_session_broadcaster

    broadcaster = get_session_broadcaster(session_id)
    return EventSourceResponse(
        broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
        ping=20,
    )


# ── Ownership Helpers ────────────────────────────────────────────────────────


def _check_ownership(session: Session, user: User) -> None:
    """Verify the user owns the session or it's a default/legacy session.

    Raises HTTPException(404) if the user doesn't own the session.
    Uses 404 (not 403) to avoid leaking session IDs to other users.

    Args:
        session: The session to check.
        user: The authenticated user.

    Raises:
        HTTPException(404): If the user doesn't own the session.
    """
    from app.foundation.config import settings
    if not settings.auth_enabled:
        return  # No ownership check when auth is disabled
    # Default/demo sessions are shared read-only templates — allow access
    if session.user_id == "__default__":
        return
    # Reject legacy sessions with no owner and sessions owned by others
    if not session.user_id or session.user_id != user.oid:
        logger.warning(
            "auth.ownership.denied",
            extra={
                "session_id": session.id,
                "user_oid": user.oid,
                "session_user_id": session.user_id,
            },
        )
        raise HTTPException(status_code=404, detail="Session not found")


def _check_not_default(session: Session, user: User, action: str) -> None:
    """Block mutation of default/demo sessions.

    Args:
        session: The session to check.
        user: The authenticated user (for logging).
        action: The action being attempted ("patch" or "delete") for logging.

    Raises:
        HTTPException(403): If the session is a default session.
    """
    if session.user_id == "__default__":
        logger.warning(
            "auth.default_session.blocked",
            extra={
                "session_id": session.id,
                "user_oid": user.oid,
                "action": action,
            },
        )
        raise HTTPException(status_code=403, detail="Cannot modify default sessions")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", response_model=Session, status_code=201)
async def create_session(
    req: CreateSessionRequest | None = None,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    from app.foundation.config import settings
    from app.foundation.request_scope import get_request_scope
    # Use per-request scope for scenario name to prevent cross-user bleed.
    # The session records which scenario was active when it was created.
    active_scenario = get_request_scope().scenario_name or settings.scenario_name
    session = Session(
        title=req.title if req else "New conversation",
        scenario_name=active_scenario,
        user_id=user.oid,
    )
    try:
        created = await store.create(session)

        # Eagerly initialize a thread for every agent defined in scenario.yaml.
        # Each thread gets its system prompt as message 0 so that agent identity
        # is established before the first user message — no lazy init, no bleed.
        from app.services.conversation import SessionStateManager
        ssm = SessionStateManager()
        await ssm.initialize_all_threads(created, created.id, store)

        logger.info(
            "auth.session.created",
            extra={"session_id": created.id, "user_oid": user.oid},
        )
        return created
    except Exception as e:
        logger.warning("Session create failed: %s", e)
        raise HTTPException(status_code=503, detail="Session store unavailable")


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    try:
        return await store.list_all(user_id=user.oid)
    except Exception as e:
        logger.warning("Session list failed: %s", e)
        raise HTTPException(status_code=503, detail="Session store unavailable")


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user)
    return session


@router.get("/{session_id}/thread/{thread_id}")
async def get_thread_messages(
    session_id: str,
    thread_id: str,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    """Lazy-load sub-agent thread messages for the overlay.

    Returns messages from a specific thread within a session. Used by the
    frontend SubAgentChatPanel to load sub-agent conversation history
    for persisted sessions (not live streaming).

    Args:
        session_id: Session identifier.
        thread_id: Thread discriminator ("orchestrator" or handoff_id).

    Returns:
        List of Message dicts matching the thread.
    """
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user)
    messages = await store.get_thread_messages(session_id, thread_id)
    return [m.model_dump(mode="json") for m in messages]


@router.patch("/{session_id}", response_model=Session)
async def update_session(
    session_id: str,
    req: UpdateSessionRequest,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user)
    _check_not_default(session, user, "patch")
    session.title = req.title
    return await store.update(session)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user)
    _check_not_default(session, user, "delete")
    await store.delete(session_id)
    remove_session_broadcaster(session_id)
    # Clean up session-scoped spoof state (network actions, tickets, etc.)
    try:
        from tools._spoof_state import reset as reset_spoof_state
        reset_spoof_state(session_id)
    except ImportError:
        pass


# ── Save / Load ──────────────────────────────────────────────────────────────


def _saved_conversations_dir() -> Path:
    """Return the saved_conversations directory for the active scenario."""
    from app.scenario import get_scenario_dir

    scenario_dir = get_scenario_dir()
    if not scenario_dir:
        raise HTTPException(
            status_code=500, detail="No active scenario configured"
        )
    d = scenario_dir / "saved_conversations"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/{session_id}/save", status_code=200)
async def save_session(
    session_id: str,
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    """Save a session to the scenario's saved_conversations/ folder as JSON."""
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    _check_ownership(session, user)

    save_dir = _saved_conversations_dir()
    # Use session ID as filename to avoid duplicates on re-save
    filepath = save_dir / f"{session.id}.json"
    data = session.model_dump(mode="json")
    filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    logger.info("Saved session %s → %s", session.id, filepath)
    return {"status": "saved", "path": str(filepath.name)}


@router.post("/reset-defaults", status_code=200)
async def reset_defaults(
    store: SessionStore = Depends(get_store),
    user: User = Depends(get_current_user),
):
    """Delete user's cloned demo sessions and re-seed from templates.

    Removes all sessions that were cloned from ``__default__`` templates
    for this user, clears the seeded-users cache, and immediately
    re-clones the templates. The next ``list_all()`` will show fresh copies.

    Returns:
        JSON with ``deleted`` (sessions removed) and ``seeded`` (new clones).
    """
    from app.foundation.config import settings
    # Skip when auth disabled — anonymous users see __default__ directly
    if not settings.auth_enabled:
        return {"deleted": 0, "seeded": 0}

    deleted = 0
    seeded = 0

    # Identify which session titles come from templates so we can delete
    # only user's cloned demo sessions (not manually created ones).
    template_titles: set[str] = set()
    if hasattr(store, "_template_ids"):
        for tid in store._template_ids:
            template = await store.get(tid)
            if template:
                template_titles.add(template.title)

    # Delete user's cloned demo sessions (sessions whose title matches templates)
    if template_titles:
        try:
            all_sessions = await store.list_all(user_id=user.oid)
            for summary in all_sessions:
                if summary.title in template_titles:
                    await store.delete(summary.id)
                    remove_session_broadcaster(summary.id)
                    deleted += 1
        except Exception as e:
            logger.warning("reset_defaults.delete_failed: %s", e)

    # Clear seeded-users cache so _ensure_user_seeded runs again
    if hasattr(store, "_seeded_users"):
        store._seeded_users.discard(user.oid)

    # Force re-seed — next list_all triggers clone, but we call it explicitly
    # so the response reflects the new state.
    if hasattr(store, "_ensure_user_seeded"):
        await store._ensure_user_seeded(user.oid)
        seeded = len(getattr(store, "_template_ids", []))

    logger.info(
        "reset_defaults.complete",
        extra={"user_oid": user.oid, "deleted": deleted, "seeded": seeded},
    )
    return {"deleted": deleted, "seeded": seeded}



