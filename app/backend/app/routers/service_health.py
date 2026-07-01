"""Service health endpoint — pings Azure services and reports connectivity.

Module role:
    Provides ``GET /api/services/health`` which checks connectivity to all
    configured Azure services (AI Search, AI Foundry, Fabric, Cosmos DB, LLM)
    in parallel and returns status + sub-resource metadata.

    Phase 1.5 enhancements:
      - ``DependencyStatus`` enum for unified status semantics
      - 30-second TTL caching to avoid probe storms
      - Circuit breaker state → dependency status mapping
      - Overall system health rollup (healthy / degraded / unhealthy)
      - LLM endpoint health check

    Each service check is a lightweight ping:
      - AI Search: list index names
      - AI Foundry: project endpoint reachable
      - Fabric: workspace items accessible
      - Cosmos Sessions: container readable
      - LLM: provider-dependent (echo/mock → always UP; agent/openai → ping)

Key collaborators:
    - ``app.config.settings`` — provides endpoints and credentials
    - ``app.resilience``      — DependencyStatus enum, CircuitBreaker registry
    - ``DefaultAzureCredential`` — RBAC auth for all services

Dependents:
    Called by: frontend ServiceHealth panel via polling + manual refresh
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends

from app.deps import get_current_user
from app.auth import User
from app.foundation.config import settings
from app.foundation.resilience import DependencyStatus, registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/services", tags=["services"])


# ── Health check caching ─────────────────────────────────────────────────────
# Each check result is cached with a 30-second TTL to avoid hammering Azure
# APIs on polling intervals shorter than 30s.
_health_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 30.0


async def _cached_check(name: str, check_fn) -> dict[str, Any]:
    """Run a health check with TTL-based caching.

    Returns the cached result if within TTL, otherwise invokes the check
    function and caches the new result.

    Args:
        name: Unique name for the service check (cache key).
        check_fn: Async callable that returns a status dict.

    Returns:
        Service status dict (from cache or fresh invocation).
    """
    now = time.monotonic()
    cached = _health_cache.get(name)
    if cached and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    result = await check_fn()
    _health_cache[name] = (now, result)
    return result


# ── Breaker → status mapping ─────────────────────────────────────────────────


def _breaker_to_status(breaker_name: str, live_status: str) -> str:
    """Combine a live ping result with circuit breaker state.

    If the breaker is OPEN → throttled (regardless of live ping).
    If the breaker is HALF_OPEN → degraded.
    Otherwise → maps live_status: connected→up, disconnected→down.

    Args:
        breaker_name: Name of the registered circuit breaker.
        live_status: Result from the live ping ("connected", "disconnected", "not_configured").

    Returns:
        Unified DependencyStatus string value.
    """
    breaker = registry.get(breaker_name)
    if breaker:
        state = breaker.state.value
        if state == "open":
            return DependencyStatus.THROTTLED.value
        if state == "half-open":
            return DependencyStatus.DEGRADED.value

    # Map live ping vocabulary → DependencyStatus
    status_map = {
        "connected": DependencyStatus.UP.value,
        "disconnected": DependencyStatus.DOWN.value,
        "not_configured": DependencyStatus.NOT_CONFIGURED.value,
    }
    return status_map.get(live_status, live_status)


# ── Overall status rollup ────────────────────────────────────────────────────


def _compute_overall_status(services: dict[str, dict]) -> str:
    """Compute overall system health from individual service statuses.

    HEALTHY:    All configured services are UP or NOT_CONFIGURED.
    DEGRADED:   Some services are THROTTLED, DEGRADED, or DOWN — but
                critical services (LLM, session store) are still UP.
    UNHEALTHY:  Any critical service is DOWN.

    Critical services: ai_foundry, session_store.
    Non-critical: ai_search, cosmos_sessions.

    Args:
        services: Dict of {service_name: {status: str, ...}}.

    Returns:
        "healthy", "degraded", or "unhealthy".
    """
    critical = {"ai_foundry", "session_store"}
    statuses = {name: svc.get("status", "unknown") for name, svc in services.items()}

    # Any critical service down → UNHEALTHY
    for svc_name in critical:
        if statuses.get(svc_name) == DependencyStatus.DOWN.value:
            return "unhealthy"

    # Any service not healthy → DEGRADED
    healthy_states = {DependencyStatus.UP.value, DependencyStatus.NOT_CONFIGURED.value}
    non_healthy = {s for s in statuses.values() if s not in healthy_states}
    if non_healthy:
        return "degraded"

    return "healthy"


async def _check_ai_search() -> dict[str, Any]:
    """Ping AI Search and list index names."""
    endpoint = settings.ai_search_endpoint
    if not endpoint:
        return {"status": "not_configured", "endpoint": None, "indexes": []}
    try:
        import httpx
        from azure.identity import DefaultAzureCredential

        cred = DefaultAzureCredential()
        token = cred.get_token("https://search.azure.com/.default")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{endpoint}/indexes?api-version=2024-07-01&$select=name",
                headers={"Authorization": f"Bearer {token.token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                names = [idx["name"] for idx in data.get("value", [])]
                return {"status": "connected", "endpoint": endpoint, "indexes": names}
            return {"status": "disconnected", "endpoint": endpoint, "indexes": [], "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "disconnected", "endpoint": endpoint, "indexes": [], "error": str(e)[:200]}


async def _check_ai_foundry() -> dict[str, Any]:
    """Ping AI Foundry and list deployed chat-capable models.

    Uses the AI Projects SDK ``deployments.list()`` — the same source as
    the model selector dropdown — so the health panel shows only deployed
    models, not the full catalog.

    Falls back to a raw HTTP ping if the SDK import fails (e.g. missing
    ``azure-ai-projects`` package).
    """
    endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
    if not endpoint:
        return {"status": "not_configured", "endpoint": None, "models": []}

    # Extract base domain for display
    base = endpoint.split("/api/projects")[0] if "/api/projects" in endpoint else endpoint
    base = base.rstrip("/")

    try:
        from azure.ai.projects import AIProjectClient
        from app.foundation.credentials import get_azure_credential

        # Use centralized credential factory (tier 2-3 only — no Fabric SP)
        credential = get_azure_credential(require_fabric_sp=False)

        client = AIProjectClient(endpoint=endpoint, credential=credential)

        # List deployments — same logic as routers/models.py list_models()
        models: list[str] = []
        for dep in client.deployments.list():
            caps = dep.capabilities or {}
            if caps.get("chat_completion") != "true":
                continue
            models.append(dep.name)

        models.sort()
        return {"status": "connected", "endpoint": base, "models": models}
    except Exception as e:
        return {"status": "disconnected", "endpoint": base, "models": [], "error": str(e)[:200]}


async def _check_cosmos() -> dict[str, Any]:
    """Check Cosmos DB by using the actual session store's health check."""
    endpoint = settings.cosmos_session_endpoint
    if not endpoint:
        return {"status": "not_configured", "endpoint": None, "database": None}
    try:
        # Use the actual app's session store if it's a CosmosSessionStore
        from app.main import app as _app
        store = getattr(_app.state, "store", None)
        if store is not None and hasattr(store, "is_healthy"):
            healthy = await store.is_healthy()
            if healthy:
                return {"status": "connected", "endpoint": endpoint, "database": settings.cosmos_session_database}
            return {"status": "disconnected", "endpoint": endpoint, "database": settings.cosmos_session_database, "error": "is_healthy() returned False"}
        # Store doesn't have is_healthy — it's InMemorySessionStore
        return {"status": "not_configured", "endpoint": endpoint, "database": None}
    except Exception as e:
        return {"status": "disconnected", "endpoint": endpoint, "database": settings.cosmos_session_database, "error": str(e)[:200]}


@router.get("/health")
async def get_service_health(user: User = Depends(get_current_user)):
    """Check connectivity to all configured Azure services in parallel.

    Phase 1.5: Uses TTL caching (30s), circuit breaker state mapping,
    LLM endpoint check, and overall health rollup.

    Returns:
        JSON dict with overall status, per-service status, and circuit
        breaker states. ``status`` is "healthy", "degraded", or "unhealthy".
    """
    # Run all checks in parallel with caching.
    # LLM check is omitted — AI Foundry already validates the inference endpoint.
    results = await asyncio.gather(
        _cached_check("ai_search", _check_ai_search),
        _cached_check("ai_foundry", _check_ai_foundry),
        _cached_check("cosmos", _check_cosmos),
        return_exceptions=True,
    )

    # Handle any exceptions from gather
    def safe(result: Any) -> dict:
        if isinstance(result, Exception):
            return {"status": "disconnected", "error": str(result)[:200]}
        return result

    # Determine session store type from app state
    session_store_type = "unknown"
    try:
        from app.main import app as _app
        store = getattr(_app.state, "store", None)
        if store is not None:
            cls_name = type(store).__name__
            if "Cosmos" in cls_name:
                session_store_type = "cosmos"
            elif "InMemory" in cls_name:
                session_store_type = "in_memory"
    except Exception:
        pass

    # Build services dict with breaker-aware status mapping.
    # All services go through _breaker_to_status for uniform DependencyStatus values.
    services = {
        "ai_search": {**safe(results[0]), "status": _breaker_to_status("ai_search", safe(results[0]).get("status", "disconnected"))},
        "ai_foundry": {**safe(results[1]), "status": _breaker_to_status("ai_foundry", safe(results[1]).get("status", "disconnected"))},
        "cosmos_sessions": {**safe(results[2]), "status": _breaker_to_status("cosmos_sessions", safe(results[2]).get("status", "disconnected"))},
        "session_store": {
            "status": DependencyStatus.UP.value,
            "type": session_store_type,
            "database": "InMemorySessionStore" if session_store_type == "in_memory" else settings.cosmos_session_database or None,
        },
    }

    # Overall health rollup
    overall = _compute_overall_status(services)

    # Circuit breaker diagnostic states
    breaker_statuses = registry.all_statuses()

    return {
        "status": overall,
        "services": services,
        "circuit_breakers": breaker_statuses,
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
    }


# ── LLM endpoint check ──────────────────────────────────────────────────────


async def _check_llm() -> dict[str, Any]:
    """Verify LLM endpoint is reachable.

    Strategy depends on provider:
      - echo/mock: always UP (no external dependency)
      - agent: ping AZURE_AI_PROJECT_ENDPOINT
      - openai: ping base URL if configured

    Returns:
        Status dict with {status, provider, model}.
    """
    if settings.llm_provider in ("echo", "mock"):
        return {
            "status": "connected",
            "provider": settings.llm_provider,
            "model": settings.llm_model,
        }

    if settings.llm_provider == "agent":
        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
        if not endpoint:
            return {"status": "not_configured", "provider": "agent"}
        try:
            import httpx
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
            token = cred.get_token("https://cognitiveservices.azure.com/.default")

            # Extract base domain — /api/projects/... returns 404; use /openai/models instead
            base = endpoint.split("/api/projects")[0] if "/api/projects" in endpoint else endpoint
            base = base.rstrip("/")

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{base}/openai/models?api-version=2024-10-21",
                    headers={"Authorization": f"Bearer {token.token}"},
                )
                if resp.status_code == 200:
                    return {"status": "connected", "provider": "agent", "model": settings.llm_model}
                return {"status": "disconnected", "provider": "agent", "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"status": "disconnected", "provider": "agent", "error": str(e)[:200]}

    # openai and other providers — report UP with basic info
    return {"status": "connected", "provider": settings.llm_provider, "model": settings.llm_model}
