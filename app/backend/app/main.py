"""FastAPI application entry point — the "main" module for the chat backend.

Module role:
    Application composition root. Initialises the FastAPI app, wires middleware,
    registers route modules, and performs one-time startup tasks (session store
    creation, LLM provider instantiation, scenario consistency verification).

Lifecycle:
    uvicorn imports ``app.main:app`` → triggers module-level code (settings load,
    logging config) → FastAPI ``lifespan`` context manager runs on first request.

Key collaborators:
    - ``app.config.settings``           – validated env-var configuration
    - ``app.services.llm``              – LLM provider factory (openai/agent/mock/echo)
    - ``app.services.session_store``    – in-memory or HTTP-backed session persistence
    - ``app.routers.chat``              – SSE streaming chat endpoint
    - ``app.routers.sessions``          – session CRUD endpoints
    - ``app.routers.scenario``          – scenario metadata + health endpoints

Dependents:
    Called by: uvicorn ASGI server (``uvicorn app.main:app``)
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.foundation.config import settings  # Singleton Settings instance — reads control/.env
from app.foundation.log_broadcaster import get_agent_broadcaster, get_backend_broadcaster
from app.observability import configure as configure_observability
from app.routers.chat import router as chat_router  # SSE streaming chat routes
from app.routers.agents import router as agents_router  # Agent definitions endpoint
from app.routers.config import router as config_router  # Config resolver API routes
from app.routers.feedback import router as feedback_router  # Bug report / feedback
from app.routers.observability import router as observability_router  # Observability SSE + status
from app.routers.scenario import scenario_router  # Scenario metadata
from app.routers.sessions import router as sessions_router  # Session CRUD routes
from app.routers.service_health import router as service_health_router  # Service health checks
from app.services.llm import create_llm_service  # Factory: settings.llm_provider → LLMService
from app.services.session_store.memory import InMemorySessionStore  # Dev/fallback session store

# Logger for this module — configured by observability.configure() below
logger = logging.getLogger(__name__)

# Shutdown event — lives in _lifecycle.py to break circular import with chat.py.
# main.py sets it during teardown; chat.py checks it during streaming.
from app.foundation._lifecycle import shutdown_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Two-phase startup: fast yield, background warm-up.

    Phase 1 (blocking, <500ms):
        Uses cached config + InMemorySessionStore so FastAPI can serve
        requests immediately. ``/health`` responds, sessions work in-memory.

    Phase 2 (background ``asyncio.Task``):
        Upgrades to Cosmos session store if healthy.
        Sets ``app.state.startup_status = "ready"`` when done.

    Side effects:
        - ``app.state.startup_status``: ``"warming"`` → ``"ready"``
        - ``app.state.store``: InMemorySessionStore → (possibly) CosmosSessionStore
    """
    logger.info("Starting — provider=%s", settings.llm_provider)
    t_startup = time.monotonic()  # Overall startup timer
    app.state.startup_status = "warming"

    # ── Phase 1: fast startup from cache ─────────────────────────────

    # 1a. Session store — always start with InMemorySessionStore (fast).
    #     Background warm-up will upgrade to Cosmos if healthy.
    t0 = time.monotonic()
    from app.scenario import get_scenario_dir
    scenario_dir = get_scenario_dir()
    app.state.store = InMemorySessionStore()
    await app.state.store.load_saved(scenario_dir)
    if hasattr(app.state.store, "_scenario"):
        app.state.store._scenario = settings.scenario_name or ""
    logger.info("startup.session_store", extra={
        "duration_ms": round((time.monotonic() - t0) * 1000),
        "backend": "InMemorySessionStore",
    })

    # 1c. LLM service — constructor only, no I/O.
    t0 = time.monotonic()
    app.state.llm = create_llm_service()
    logger.info("startup.llm_service", extra={
        "duration_ms": round((time.monotonic() - t0) * 1000),
        "provider": settings.llm_provider,
    })

    # 1c2. LLMOps tracing — background export worker (Phase 1.1).
    #      Returns None when LLMOPS_BACKEND is empty (zero overhead).
    from app.llmops import configure_llmops
    app.state.llmops = configure_llmops()

    # 1c3. Guardrails — load from scenario.yaml (Phase 1.6).
    #      Empty lists when scenario has no guardrails configured.
    try:
        from app.scenario import load_scenario_yaml
        from app.guardrails._registry import resolve_guardrails
        _scenario_yaml = load_scenario_yaml()
        _agent_cfg = _scenario_yaml.get("agents", {}).get("orchestrator", {})
        app.state.input_guardrails = resolve_guardrails(
            _agent_cfg.get("input_guardrails", [])
        )
        app.state.output_guardrails = resolve_guardrails(
            _agent_cfg.get("output_guardrails", [])
        )
        if app.state.input_guardrails or app.state.output_guardrails:
            logger.info(
                "startup.guardrails: %d input, %d output",
                len(app.state.input_guardrails),
                len(app.state.output_guardrails),
            )
    except Exception as e:
        logger.warning("startup.guardrails_failed: %s — no guardrails loaded", e)
        app.state.input_guardrails = []
        app.state.output_guardrails = []


    # 1e. Scenario consistency check (non-blocking, reads disk).
    _check_scenario_consistency()

    # 1e. Observability: wire LogBroadcaster handlers to Python loggers.
    agent_bc = get_agent_broadcaster()
    logging.getLogger("app.services.llm.agent").addHandler(agent_bc.get_handler())
    logging.getLogger("agents").addHandler(agent_bc.get_handler())
    logging.getLogger("tools").addHandler(agent_bc.get_handler())  # captures all tools.*

    backend_bc = get_backend_broadcaster()
    logging.getLogger("uvicorn.access").addHandler(backend_bc.get_handler())
    logging.getLogger("httpx").addHandler(backend_bc.get_handler())
    logging.getLogger("azure.core.pipeline").addHandler(backend_bc.get_handler())
    logger.info("Observability broadcasters wired")

    # 1f. Launch background warm-up — completes Phase 2 while serving requests.
    warmup_task = asyncio.create_task(
        _background_warmup(app, scenario_dir),
        name="startup-warmup",
    )

    logger.info("startup.phase1_complete", extra={
        "duration_ms": round((time.monotonic() - t_startup) * 1000),
    })

    yield  # ── Application serves requests ─────────────────────────────

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Shutting down — draining active connections")
    shutdown_event.set()  # Signal active SSE generators to stop accepting new events

    # Cancel background warm-up if still running (e.g., very slow Azure)
    if not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            logger.info("Background warm-up cancelled during shutdown")

    # ── Resource cleanup ─────────────────────────────────────────────────
    # Close session store connection (Cosmos client or noop for in-memory)
    if hasattr(app.state.store, "close"):
        await app.state.store.close()
        logger.info("Session store closed")

    # Drain and close LLMOps trace manager (Phase 1.1)
    if getattr(app.state, "llmops", None):
        await app.state.llmops.close()
        logger.info("LLMOps trace manager closed")

    # Flush OTel spans/metrics before process exit via the shutdown function
    # that calls TracerProvider.shutdown() and MeterProvider.shutdown().
    try:
        from app.observability import shutdown_observability
        shutdown_observability()
        logger.info("OTel providers shut down")
    except Exception:
        pass  # OTel not configured or already shut down

    logger.info("Shutdown complete")


async def _background_warmup(app: FastAPI, scenario_dir) -> None:
    """Phase 2: background warm-up — Cosmos session store upgrade.

    Runs as an ``asyncio.Task`` after lifespan yields. Non-fatal — if any
    step fails, the app continues on InMemorySessionStore.

    Args:
        app: FastAPI app instance — mutates ``app.state``.
        scenario_dir: Path to scenario dir for session seeding.

    Side effects:
        - May swap ``app.state.store`` from InMemory to CosmosSessionStore.
        - Registers Cosmos circuit breaker in resilience registry.
        - Sets ``app.state.startup_status = "ready"``.
    """
    t_warmup = time.monotonic()
    logger.info("startup.warmup_started")

    # ── 2a. Cosmos session store upgrade ─────────────────────────────
    # Attempt to upgrade from InMemorySessionStore to CosmosSessionStore.
    # Only if COSMOS_SESSION_ENDPOINT is configured (via settings or env var).
    t0 = time.monotonic()
    cosmos_endpoint = settings.cosmos_session_endpoint
    if not cosmos_endpoint:
        import os
        cosmos_endpoint = os.environ.get("COSMOS_SESSION_ENDPOINT", "")

    if cosmos_endpoint:
        try:
            from app.services.session_store.cosmos import CosmosSessionStore
            store = CosmosSessionStore(
                endpoint=cosmos_endpoint,
                database=settings.cosmos_session_database,
                container=settings.cosmos_session_container,
            )
            healthy = await store.is_healthy(timeout=2.0)
            if healthy:
                # Swap store — safe because deps.py reads app.state.store per-request
                app.state.store = store
                if hasattr(store, "_scenario"):
                    store._scenario = settings.scenario_name or ""
                # Register circuit breaker in resilience registry — required
                # for /api/services/health to report Cosmos breaker state
                from app.foundation.resilience import registry as _resilience_registry
                _resilience_registry._breakers["cosmos_sessions"] = store._breaker
                # Seed saved conversations into Cosmos (idempotent)
                await store.seed_saved_conversations(scenario_dir)
                logger.info("startup.warmup.cosmos_upgraded", extra={
                    "duration_ms": round((time.monotonic() - t0) * 1000),
                    "endpoint": cosmos_endpoint,
                })
            else:
                logger.info("startup.warmup.cosmos_unhealthy — staying on in-memory")
                await store.close()
        except Exception as e:
            logger.warning("startup.warmup.cosmos_failed: %s — staying on in-memory", e)
    else:
        logger.info("startup.warmup.cosmos_skipped — no endpoint configured")

    # ── 2b. Mark ready ───────────────────────────────────────────────
    app.state.startup_status = "ready"
    logger.info("startup.warmup_complete", extra={
        "duration_ms": round((time.monotonic() - t_warmup) * 1000),
        "session_store": type(app.state.store).__name__,
    })


def _check_scenario_consistency() -> None:
    """Validate required config at startup.

    Boot-time config validation — fail-fast with batch errors.
    """
    try:
        from app.scenario import load_scenario_yaml
        from app.foundation.boot_validation import validate_boot_config
        scenario_yaml = load_scenario_yaml()
        errors = validate_boot_config(scenario_yaml, settings)
        if errors:
            logger.warning(
                "boot.config_errors: %d missing config key(s) detected. "
                "Some features may be unavailable:\n  • %s",
                len(errors),
                "\n  • ".join(errors),
            )
        else:
            logger.info("boot.config_validation: all required keys present")
    except Exception as e:
        logger.warning("boot.config_validation_failed: %s", e)


# ── FastAPI application instance ──────────────────────────────────────────────
# The ``lifespan`` callback runs before the first request and after the last.

app = FastAPI(
    title="LLM Conversational UI — API",
    description="Model pattern for LLM chat applications",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Observability ────────────────────────────────────────────────────────────
# Sets up JSON structured logging, correlation IDs, and OTel auto-instrumentation.
# Export target is controlled by OTEL_EXPORT_TARGET env var (default: noop).
configure_observability(app)

# ── Middleware ───────────────────────────────────────────────────────────────
# CORS is required because the Vite dev server (port 5173) calls the FastAPI
# backend (port 9000) cross-origin. In production behind a reverse proxy,
# both share the same origin and CORS is not needed.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Default: localhost:5173, localhost:3000
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Ed25519 dev-sign side-channel (lineage: GridIQ/vm_agent) ─────────────────
# Mounts the agentkit signed-request ASGI middleware ONLY when
# DEV_PUBLIC_KEY_ED25519 is configured. Lets headless CI/agent probes drive an
# auth-gated deployment without an interactive Entra login. Fail-closed: no key
# = not mounted = no bypass. Sign with `python -m agentkit.dev_tools.dev_sign`.
from agentkit.hosting.devauth import install_signed_request_auth  # noqa: E402
from app.auth import User  # noqa: E402

_devsign_mounted = install_signed_request_auth(
    app,
    public_key_b64=settings.dev_public_key_ed25519,
    identity_factory=lambda slug: User(
        oid=f"devsign:{slug or 'probe'}",
        email="dev-sign@local",
        name="DevSign Probe",
    ),
)
if _devsign_mounted:
    logging.getLogger(__name__).info("auth.devsign.mounted")


# ── Per-request context middleware ───────────────────────────────────────────
# Delegates to _middleware.py: three-tier resolution for scenario/backend/model.
from app._middleware import set_request_context_middleware  # noqa: E402

app.middleware("http")(set_request_context_middleware)

# ── Routers ──────────────────────────────────────────────────────────────────
# All API routes live under /api/* prefix.

app.include_router(sessions_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(scenario_router, prefix="/api")
app.include_router(observability_router, prefix="/api")
app.include_router(service_health_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(feedback_router, prefix="/api")

from app.routers.catalog import router as catalog_router  # noqa: E402
app.include_router(catalog_router, prefix="/api")

# Auth setup + health probes — extracted to dedicated routers
from app.routers.auth_setup import router as auth_setup_router  # noqa: E402
from app.routers.health import router as health_router  # noqa: E402

app.include_router(auth_setup_router, prefix="/api")
app.include_router(health_router)
