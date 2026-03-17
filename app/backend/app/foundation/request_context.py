"""Per-request scenario/backend context — async-safe, user-isolated.

Module role:
    Provides a ``contextvars.ContextVar`` that holds the active scenario name,
    graph backend, and LLM model for the current request. Each concurrent async
    task gets its own copy, preventing cross-user state bleed.

    Replaces reading ``os.environ["SCENARIO_NAME"]``,
    ``os.environ["GRAPH_BACKEND"]``, and ``os.environ["LLM_MODEL"]``
    at call sites. Env vars remain the *default* for requests without
    headers (health checks, scripts).

How it works:
     1. Frontend sends the selected ``X-Scenario-Name`` header
     2. FastAPI middleware resolves the effective backend and model for that
         scenario, then sets the ContextVar at the start of each request
     3. Agent loader, tool functions, and routers read from the ContextVar
       via ``get_scenario_name()``, ``get_graph_backend()``, ``get_llm_model()``
    4. After the request completes, the ContextVar is automatically cleaned
       up by Python's contextvars mechanism

Key collaborators:
    - app/main.py               — registers the middleware
    - app/routers/scenarios.py  — reads/returns context values
    - app/routers/backends.py   — reads/returns context values
    - agents (AgentRegistry)    — reads scenario/backend for agent build
    - tools/graph_explorer/     — reads graph_backend for query routing

Dependents:
    Called by: any code that needs the current request's scenario or backend
"""

from __future__ import annotations

import contextvars
import os
from dataclasses import dataclass, field

# ── Context variable ─────────────────────────────────────────────────────────
# Each async task (i.e., each HTTP request) gets its own copy of this var.
# No locking needed — contextvars is designed for this purpose.

_request_ctx: contextvars.ContextVar["RequestContext"] = contextvars.ContextVar(
    "request_context"
)


@dataclass
class RequestContext:
    """Per-request state: scenario name + graph backend + LLM model.

    Attributes:
        scenario_name: Active scenario for this request. Read from
            X-Scenario-Name header or env var fallback.
        graph_backend: Effective graph backend for this request. Resolved by
            middleware from the scenario manifest, backend availability, and
            env var fallback when no request context exists.
        llm_model: Effective LLM model deployment for this request. Resolved
            by middleware for HTTP requests or read from env vars outside a
            request context.
        session_id: Current chat session ID. Set by the chat router before
            LLM invocation — gives tools access to session-scoped state.
    """

    scenario_name: str = ""
    llm_model: str = ""
    session_id: str = ""
    language: str = "en"  # ISO 639-1 code from X-User-Language header


def get_request_context() -> RequestContext:
    """Return the current request's context, or a fallback from env vars.

    Safe to call from anywhere — tool functions, services, loaders.
    If no middleware has set the context (e.g., during startup or tests),
    falls back to reading from os.environ.

    Returns:
        RequestContext with scenario_name and graph_backend.
    """
    try:
        return _request_ctx.get()
    except LookupError:
        # No context set — fall back to env vars (startup, background tasks, unit tests)
        return RequestContext(
            scenario_name=os.environ.get("SCENARIO_NAME", ""),
            llm_model=os.environ.get("LLM_MODEL", ""),
        )


def get_scenario_name() -> str:
    """Shorthand: return the current request's scenario name."""
    return get_request_context().scenario_name


def get_graph_backend() -> str:
    """Return the graph backend ID. Always 'fabric'."""
    return "fabric"


def get_language() -> str:
    """Shorthand: return the current request's target response language."""
    return get_request_context().language


def get_llm_model() -> str:
    """Shorthand: return the current request's LLM model deployment name."""
    return get_request_context().llm_model


def get_session_id() -> str:
    """Shorthand: return the current request's session ID.

    Used by spoofed action tools to key state per session.
    Returns empty string outside of a request context.
    """
    return get_request_context().session_id


def set_request_context(ctx: RequestContext) -> contextvars.Token:
    """Set the request context for the current async task.

    Called by the middleware at request start. Returns a token that can
    be used to reset the context (though cleanup is automatic).

    Args:
        ctx: The RequestContext to set.

    Returns:
        A contextvars.Token for optional manual reset.
    """
    return _request_ctx.set(ctx)
