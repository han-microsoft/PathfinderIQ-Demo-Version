"""Per-request context middleware — extracted from main.py.

Module role:
    Contains the per-request context middleware. Reads the active scenario
    from the SCENARIO_NAME env var (single-scenario mode), builds a frozen
    RequestScope, and stores both in contextvars for downstream code.

Key collaborators:
    - app.foundation.request_context — RequestContext dataclass + set_request_context()
    - app.foundation.request_scope   — build_request_scope() + set_request_scope()
    - app.foundation.config          — settings.scenario_name fallback

Dependents:
    Registered by: app.main (middleware registration)
"""

from __future__ import annotations

import base64
import json as _json
import logging
import os

from app.foundation.config import settings

logger = logging.getLogger(__name__)

# Module-level cache for the built RequestScope. In single-scenario mode
# (production), the scope never changes between requests — caching avoids
# re-parsing scenario.yaml and rebuilding configs on every request.
_cached_scope = None
_cached_scope_key: str = ""


async def set_request_context_middleware(request, call_next):
    """Set per-request context with three-tier resolution.

    Tier 1: Request header (most specific — set by frontend on every call).
    Tier 2: User preferences (for page-load requests with no header).
    Tier 3: Operator defaults from env vars / settings.

    Args:
        request: The incoming Starlette/FastAPI request.
        call_next: The next middleware or route handler in the chain.

    Returns:
        The response from the downstream handler.

    Side effects:
        Sets the RequestContext contextvar for this request's async task.
    """
    from app.foundation.request_context import RequestContext, set_request_context

    # Scenario determined from env var / settings (single-scenario mode)
    scenario = os.environ.get("SCENARIO_NAME", settings.scenario_name or "")

    # Language from frontend header — allowlisted to prevent injection
    _ALLOWED_LANGS = frozenset({"en", "ja", "ko", "zh", "ms", "th"})
    raw_lang = request.headers.get("x-user-language", "en").lower()[:5]
    language = raw_lang if raw_lang in _ALLOWED_LANGS else "en"

    ctx = RequestContext(
        scenario_name=scenario,
        llm_model="",
        language=language,
    )
    set_request_context(ctx)

    # Build the frozen RequestScope — resolves scenario.yaml, extracts all
    # service configs once. Cached per scenario name so repeated requests
    # skip YAML parsing and config extraction entirely.
    from app.foundation.request_scope import build_request_scope, set_request_scope
    global _cached_scope, _cached_scope_key
    if _cached_scope is None or _cached_scope_key != scenario:
        _cached_scope = build_request_scope(scenario_name=scenario)
        _cached_scope_key = scenario
    set_request_scope(_cached_scope)

    return await call_next(request)


def _extract_user_oid(request) -> str | None:
    """Lightweight JWT payload peek — extract user OID without full validation.

    Decodes the JWT payload (base64, no signature check) to extract the ``oid``
    claim. This is safe because the full ``get_current_user()`` dependency
    validates the token in the endpoint handler. The middleware only needs
    the OID for preference lookup.

    Args:
        request: The incoming Starlette/FastAPI request.

    Returns:
        The user's OID string, or None if no valid token present.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        # No token — check for anonymous user (AUTH_ENABLED=false).
        # In anonymous mode, all requests get the same OID ("anonymous").
        if not settings.auth_enabled:
            return "anonymous"
        return None
    token = auth_header[7:]
    try:
        # JWT is three base64url-encoded parts separated by dots.
        # The payload is the second part (index 1).
        parts = token.split(".")
        if len(parts) < 2:
            return None
        # Add padding to base64url string (JWT omits padding '=')
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("oid")
    except Exception:
        return None
