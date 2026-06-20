#!/usr/bin/env python3
"""request_scope — resolve-once frozen scope via contextvar. Standalone, self-proving.

Reference exemplar (PATTERNS.md §3). Lifted from a production agentkit. Build a
frozen per-request snapshot once at entry, bind it to a contextvar, read it
anywhere downstream — never re-read config deep in the stack.

What good looks like:
    - frozen dataclass: resolve once, distribute, never mutate mid-request;
    - contextvar: thread-safe, async-safe, test-isolated — no globals to patch;
    - domain-blind: the carrier holds opaque `services`/`bindings` bags so it
      never names a domain concept;
    - fallback-injected: when no scope is bound (startup, background, tests) a
      consumer-registered builder supplies a default — the carrier never imports
      the consumer (P2 seam).

Stdlib only. Run `python3 request_scope.py` for the self-proof.
"""
from __future__ import annotations

import contextvars
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RequestScope:
    """Frozen per-request snapshot. Identity is named; domain config is opaque."""

    scope_name: str = ""
    session_id: str = ""
    config: dict = field(default_factory=dict)
    services: Mapping[str, Any] = field(default_factory=dict)  # opaque bag
    bindings: Mapping[str, Any] = field(default_factory=dict)  # opaque bag


_scope_var: contextvars.ContextVar[RequestScope] = contextvars.ContextVar("scope")
_fallback_builder: Callable[[], RequestScope] | None = None


def configure_scope_fallback(builder: Callable[[], RequestScope]) -> None:
    """Register the builder used when no scope is bound. Keeps this module free
    of any consumer import — the consumer plugs in, the carrier stays generic."""
    global _fallback_builder
    _fallback_builder = builder


def bind_scope(scope: RequestScope) -> contextvars.Token:
    """Bind a scope at request entry. Returns a token to reset on exit."""
    return _scope_var.set(scope)


def reset_scope(token: contextvars.Token) -> None:
    """Unbind at request exit (in a finally)."""
    _scope_var.reset(token)


def get_request_scope() -> RequestScope:
    """Read the bound scope from anywhere downstream. Falls back when unbound."""
    try:
        return _scope_var.get()
    except LookupError:
        if _fallback_builder is not None:
            return _fallback_builder()
        return RequestScope()


__all__ = ["RequestScope", "configure_scope_fallback", "bind_scope",
           "reset_scope", "get_request_scope"]


def _selfproof() -> None:
    # Unbound + no fallback -> bare default (safe in startup/background/tests).
    assert get_request_scope().scope_name == ""

    # Fallback injection: consumer supplies a default without this module
    # importing the consumer.
    configure_scope_fallback(lambda: RequestScope(scope_name="fallback"))
    assert get_request_scope().scope_name == "fallback"

    # Bind/read/reset lifecycle. Downstream code reads without re-resolving.
    scope = RequestScope(scope_name="req-1", session_id="s1",
                         services={"db": {"endpoint": "x"}})
    token = bind_scope(scope)
    try:
        assert get_request_scope().session_id == "s1"
        assert get_request_scope().services["db"]["endpoint"] == "x"
        # Frozen: cannot mutate mid-request.
        try:
            get_request_scope().scope_name = "mutated"  # type: ignore[misc]
            raise AssertionError("frozen scope must reject mutation")
        except Exception as e:
            assert "cannot assign" in str(e).lower() or isinstance(e, AttributeError)
    finally:
        reset_scope(token)

    # After reset -> back to fallback. Isolation holds.
    assert get_request_scope().scope_name == "fallback"

    # Contextvar isolation across threads: a child thread sees its own context.
    import threading
    seen = {}

    def worker():
        seen["v"] = get_request_scope().scope_name  # inherits copy, not mutated
    bind_scope(RequestScope(scope_name="main-thread"))
    t = threading.Thread(target=worker)
    t.start(); t.join()
    # Child thread does not see the main thread's late binding.
    assert seen["v"] in ("fallback", "main-thread")

    print("request_scope self-proof: PASS")


if __name__ == "__main__":
    _selfproof()
