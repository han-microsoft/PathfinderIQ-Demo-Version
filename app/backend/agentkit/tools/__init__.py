"""agentkit.tools — generic, domain-blind tool-construction helpers.

This package holds reusable machinery for building agent tools without
re-implementing the connect → validate → gate → execute → shape → envelope
spine in every tool module.

Sub-packages:
    adapters — datasource adaptors (KQL / Gremlin / Azure AI Search /
               Fabric GQL / bearer-token HTTP). Each owns the transport
               spine; the *consumer* supplies the query text, the input
               sanitisation, the read-only guard, and (critically) the
               domain projection of the raw result. The adaptor never bakes
               a domain projection in — that would drag consumer vocabulary
               into agentkit and break the data boundary.

Tool decorator:
    :func:`tool` is the agentkit-owned, SDK-free decorator a tool author uses
    in place of the concrete SDK's ``@tool``. It only *stamps* agent-callable
    metadata (``fn.__agentkit_tool__``) and returns the function UNWRAPPED. The
    concrete SDK binding (Microsoft Agent Framework today) is applied later, at
    agent-build time, by ``agentkit.sdk.maf_client.bind_tools`` — so the same
    tool script works against MAF, the echo/mock client, or a future SDK with
    no edit. This keeps this module importable with zero ``agent_framework`` at
    load (the ``hello_agent`` echo example imports it clean).

Layer rule: this package imports ONLY ``agentkit.contracts``,
``agentkit.config``, ``agentkit.resilience``, ``agentkit.cloud``, optional
backend SDKs (gated as pip extras), and stdlib. It MUST NOT import any
consumer package (for GridIQ: ``foundation``, ``tools``, ``agent``,
``hosting``, ``app``, ``ops``). The :func:`tool` decorator itself is
stdlib-only — it imports NO SDK at module load.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


def tool(
    *,
    approval_mode: str = "never_require",
    description: str | None = None,
) -> Callable[[_F], _F]:
    """Stamp agent-callable metadata on a tool function (SDK-free).

    This is the agentkit-owned replacement for the concrete SDK's ``@tool``
    decorator. It does NOT wrap the function — it returns the same callable
    object with a ``__agentkit_tool__`` marker dict attached. The concrete SDK
    binding happens later at agent-build time
    (``agentkit.sdk.maf_client.bind_tools``), which reads the marker and applies
    the real SDK ``@tool(approval_mode=...)``. A non-MAF client (echo/mock)
    ignores the marker and uses the raw callable.

    Because the function is returned unwrapped, this decorator composes with
    inner decorators (e.g. ``@traced_tool``): place ``@tool`` OUTERMOST exactly
    where the SDK ``@tool`` sat, so the SDK binding wraps the fully-decorated
    callable at build time — byte-identical to the prior import-time wrapping.

    Args:
        approval_mode: Forwarded to the SDK ``@tool`` at bind time (GridIQ tools
            use ``"never_require"``). The marker carries it so the SDK binding
            reproduces the exact approval semantics.
        description: Optional explicit tool description. Defaults to the
            function's docstring when omitted.

    Returns:
        A decorator that attaches ``fn.__agentkit_tool__`` and returns ``fn``
        unchanged (same object, same signature, same behaviour).
    """

    def decorator(fn: _F) -> _F:
        # Stamp the marker; do NOT wrap. Identity + signature + behaviour are
        # preserved so stacked decorators and the live tool-call path are
        # unaffected (inc5/inc6 dropped-symbol landmine).
        fn.__agentkit_tool__ = {  # type: ignore[attr-defined]
            "approval_mode": approval_mode,
            "description": description or fn.__doc__,
        }
        return fn

    return decorator


__all__ = ["tool"]
