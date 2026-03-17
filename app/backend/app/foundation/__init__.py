"""Foundation package — Level 0 modules with zero internal dependencies.

Package role:
    Contains the base-layer modules that every other layer depends on
    but that themselves import nothing from the application. This is the
    bottom of the dependency hierarchy:

        foundation/ (L0) → imported by everything, imports nothing internal

    Modules:
        models.py          — Pydantic API contract (Message, Session, StreamEvent, etc.)
        config.py          — pydantic-settings Settings singleton
        errors.py          — ErrorCode enum, classify_error(), make_error_event()
        resilience.py      — CircuitBreaker, CircuitBreakerRegistry, DependencyStatus
        request_context.py — Per-request contextvars (scenario, backend, model)
        log_broadcaster.py — SSE fan-out for observability log streams
        _lifecycle.py      — shutdown_event (shared between main.py and chat router)

Design rationale:
    By isolating these modules into a separate package with a strict
    "no upward imports" rule, we prevent circular dependencies and
    make it possible for tools/ (L4) to import foundation types without
    pulling in the entire app/ tree.

Import convention:
    New code should import from ``app.foundation.*``:
        from app.foundation.models import Message, Session
        from app.foundation.config import settings

    Backward-compatible shims at the old paths (``app.models``, etc.)
    re-export everything so existing code continues to work.
"""
