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

from app.foundation.config import settings

logger = logging.getLogger(__name__)

# Bounded per-scenario RequestScope cache. Each scenario's scope is built once
# (scenario.yaml parse + config extraction) and reused across requests, so
# alternating users on different scenarios never thrash a single-entry cache.
_scope_cache: dict[str, object] = {}
_SCOPE_CACHE_MAX = 8


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
    from app.scenario import get_scenario_dir

    # Scenario resolution (three-tier):
    #   Tier 1: X-Scenario-Name request header (frontend selector).
    #   Tier 2: the user's saved preference (page refresh with no header).
    #   Tier 3: operator default from SCENARIO_NAME env / settings.
    # Every candidate is validated with a fresh on-disk, path-traversal-guarded
    # check so a stale catalog cache can never hide a valid pack nor admit an
    # invalid one. ``settings.scenario_name`` already binds SCENARIO_NAME (env
    # is read once at startup via pydantic-settings), so it is the single source
    # of truth for the operator default — no direct os.environ read here.
    scenario = settings.scenario_name or ""
    requested = (request.headers.get("x-scenario-name", "") or "").strip()
    if requested:
        if get_scenario_dir(requested) is not None:
            scenario = requested
        else:
            logger.warning("middleware.scenario_header_rejected: %s", requested)
    else:
        # Tier 2 — saved user preference (resolved by lightweight OID peek).
        try:
            oid = _extract_user_oid(request)
            if oid:
                from app.services.preferences import get_preferences_store
                pref = get_preferences_store(request).get_scenario(oid)
                if pref and pref != scenario and get_scenario_dir(pref) is not None:
                    scenario = pref
        except Exception as exc:  # noqa: BLE001 — never fail a request on pref lookup
            logger.warning("middleware.preference_lookup_error: %s", exc)

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
    # service configs once. Cached per scenario name (bounded) so repeated
    # requests — including rapid A/B swaps — skip YAML parse + config extraction.
    from app.foundation.request_scope import build_request_scope, set_request_scope
    scope = _scope_cache.get(scenario)
    if scope is None:
        scope = build_request_scope(scenario_name=scenario)
        if len(_scope_cache) >= _SCOPE_CACHE_MAX:
            _scope_cache.pop(next(iter(_scope_cache)))
        _scope_cache[scenario] = scope
    set_request_scope(scope)

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
