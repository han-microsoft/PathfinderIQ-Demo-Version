"""Request-scoped tool execution ledger (semantic duplicate guard).

Module role:
    Provides a context-local ledger for semantic tool calls that must not be
    repeated within one chat turn. Tool modules use this to return a visible,
    structured duplicate result instead of re-querying the same backend and
    letting an agent loop on identical evidence.

Layering:
    Pure stdlib (``contextvars``). Imports no GridIQ package and no SDK. Lifted
    from GridIQ ``foundation.tool_guard`` (E3 residual) into agentkit during the
    Inc11b cleanliness pass — the ledger is generic agent plumbing, not domain.

Opt-in:
    Outside chat streaming there may be no current ledger; direct tool
    invocations then continue unguarded (``record_tool_call_once`` returns
    ``False``).
"""

from __future__ import annotations

import contextvars
from typing import Any

_tool_call_ledger: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "tool_call_ledger",
    default=None,
)


def set_tool_call_ledger(ledger: dict[str, int] | None) -> contextvars.Token:
    """Set the per-request semantic tool-call ledger."""
    return _tool_call_ledger.set(ledger)


def reset_tool_call_ledger(token: contextvars.Token) -> None:
    """Restore the previous per-request semantic tool-call ledger."""
    _tool_call_ledger.reset(token)


def record_tool_call_once(tool_name: str, *key_parts: Any, max_calls: int = 1) -> bool:
    """Record one semantic tool call and return True when the limit is exceeded.

    The ledger is opt-in: outside chat streaming there may be no current
    ledger, and direct tool invocations continue unguarded.
    """
    ledger = _tool_call_ledger.get(None)
    if ledger is None:
        return False
    key = "|".join([tool_name, *(str(part).strip().lower() for part in key_parts)])
    count = ledger.get(key, 0)
    ledger[key] = count + 1
    return count >= max_calls


__all__ = [
    "set_tool_call_ledger",
    "reset_tool_call_ledger",
    "record_tool_call_once",
]
