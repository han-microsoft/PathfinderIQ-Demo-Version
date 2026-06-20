"""agentkit.config.request_scope — frozen per-request scope carrier.

Module role:
    The domain-blind "resolve-once, freeze, distribute" per-request snapshot.
    Built once at request start, bound to a contextvar, and read by tools /
    agents / routers without re-reading config deep in the stack.

    The carrier is generic: it holds request identity (``scope_name``,
    ``llm_model``, ``session_id``), a ``settings`` reference, a ``prompts_dir``,
    the raw ``config`` dict, and two **opaque bags** — ``services`` and
    ``bindings`` — into which a consumer projects its domain-specific service
    configs (e.g. GridIQ puts ``services["fabric"]`` and
    ``bindings["search_indexes"]``). The carrier never names a domain service.

Fallback builder injection:
    ``get_request_scope()`` returns the bound scope, or — when none is bound
    (startup, background tasks, unit tests) — calls the fallback builder the
    consumer registered via ``configure_scope_fallback(fn)``. If no fallback is
    registered, a bare default ``RequestScope`` is returned. This keeps agentkit
    from importing any consumer package to build a domain scope.

Layer rule:
    stdlib only. Never imports a consumer package.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RequestScope:
    """Frozen per-request snapshot — resolved once, distributed everywhere.

    Attributes:
        scope_name:   Logical scope identity (GridIQ: active scenario name).
        llm_model:    Resolved LLM model (empty = per-agent default).
        session_id:   Chat session id (empty for non-chat requests).
        config:       Raw parsed config dict (GridIQ: agent_config.yaml).
        prompts_dir:  Absolute path to the prompts directory.
        services:     Opaque map of domain service configs, keyed by name.
        bindings:     Opaque map of domain data bindings, keyed by name.
        settings:     Reference to the process settings instance.
    """

    scope_name: str = ""
    llm_model: str = ""
    session_id: str = ""
    config: dict = field(default_factory=dict)
    prompts_dir: Path = field(default_factory=lambda: Path("."))
    services: Mapping[str, Any] = field(default_factory=dict)
    bindings: Mapping[str, Any] = field(default_factory=dict)
    settings: Any = None


# ── Contextvars ──────────────────────────────────────────────────────────────

_scope_var: contextvars.ContextVar[RequestScope] = contextvars.ContextVar("request_scope")
_session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_session_id", default=""
)

# Consumer-registered fallback builder (no request bound → build a default).
_fallback_builder: Callable[[], RequestScope] | None = None


def configure_scope_fallback(builder: Callable[[], RequestScope]) -> None:
    """Register the fallback scope builder used when no scope is bound.

    Called by the consumer (e.g. GridIQ's ``foundation.request_scope`` at import
    time). Keeps agentkit free of any consumer import.
    """
    global _fallback_builder
    _fallback_builder = builder


def get_request_scope() -> RequestScope:
    """Return the current request's frozen scope.

    Safe from tools, agents, routers, services. Falls back to the registered
    fallback builder (or a bare default ``RequestScope``) when no scope is bound.
    """
    try:
        return _scope_var.get()
    except LookupError:
        if _fallback_builder is not None:
            return _fallback_builder()
        return RequestScope()


def set_request_scope(scope: RequestScope) -> contextvars.Token:
    """Bind the request scope for the current async task. Returns a reset token."""
    return _scope_var.set(scope)


def reset_request_scope(token: contextvars.Token) -> None:
    """Reset the scope contextvar to its previous value."""
    _scope_var.reset(token)


def get_session_id() -> str:
    """Return the current request's session id, or empty if unset."""
    return _session_id_var.get()


def set_session_id(session_id: str) -> contextvars.Token:
    """Bind the session id for the current async task. Returns a reset token."""
    return _session_id_var.set(session_id)


def reset_session_id(token: contextvars.Token) -> None:
    """Reset the session-id contextvar to its previous value."""
    _session_id_var.reset(token)
