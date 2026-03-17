"""Health check router — liveness and readiness probes.

Module role:
    Provides ``/health`` (liveness) and ``/health/ready`` (readiness) endpoints.
    These are used by Azure Container Apps probes, Kubernetes probes, and
    operational dashboards.

    The liveness probe always returns 200 — if the process can respond, it's alive.
    The readiness probe returns 503 during warm-up, then runs deep checks
    (session store, scenario, circuit breakers) once ready.

Key collaborators:
    - app.config.settings — reads llm_provider for liveness response
    - app.scenario — validates scenario is loaded
    - app.services.session_store — validates store connectivity

Dependents:
    Called by: Container Apps probes, /health/ready dashboards
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.foundation.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    """Liveness probe — always returns 200.

    Returns startup_status so callers can distinguish between
    "serving but still warming up" and "fully ready".
    """
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "startup_status": getattr(request.app.state, "startup_status", "unknown"),
    }


@router.get("/health/ready")
async def readiness(request: Request):
    """Deep health check — validates all backend dependencies.

    Returns 200 if all checks pass, 503 if any are degraded.
    Used by Container Apps readiness probes and operational dashboards.
    """
    # Fast reject during warm-up — readiness probe should return 503
    # until background initialisation is complete.
    startup_status = getattr(request.app.state, "startup_status", "unknown")
    if startup_status != "ready":
        return JSONResponse(
            content={
                "status": "warming",
                "startup_status": startup_status,
                "detail": "Background initialisation in progress",
            },
            status_code=503,
        )

    checks = {}

    # Session store connectivity
    try:
        await request.app.state.store.list_all()
        checks["session_store"] = {"status": "ok"}
    except Exception as e:
        checks["session_store"] = {"status": "error", "detail": str(e)[:200]}

    # Scenario loaded
    from app.scenario import get_scenario_dir
    scenario_dir = get_scenario_dir()
    checks["scenario"] = {
        "status": "ok" if scenario_dir else "error",
        "name": settings.scenario_name,
    }

    # Fabric circuit breaker state
    from app.scenario._registry import get_fabric_throttle_status
    fabric_status = get_fabric_throttle_status()
    if fabric_status:
        checks["fabric_circuit_breaker"] = {"status": fabric_status.get("state", "unknown")}
    else:
        checks["fabric_circuit_breaker"] = {"status": "not_configured"}

    overall = "ok" if all(
        c.get("status") in ("ok", "not_configured", "closed")
        for c in checks.values()
    ) else "degraded"
    return JSONResponse(
        content={"status": overall, "checks": checks},
        status_code=200 if overall == "ok" else 503,
    )
