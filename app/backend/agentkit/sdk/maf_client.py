"""Microsoft Agent Framework (MAF) SDK client — the one concrete SDK binding.

Module role:
    Holds every direct ``agent_framework`` import the agent runtime needs:
    the composed compaction strategy and the tool-tracing middleware. Core
    modules (``compaction``, ``middleware``) call the builders here so the SDK
    import surface is one file. ``agentkit.core`` imports nothing from this
    module at import time — the builders are called lazily at runtime.

Why isolated:
    copilot-instructions §Runtime Discipline rule 6 (isolate SDK quirks in
    adapters) + §3.3 of genericize/TIER1_EXTRACTION_PLAN.md. Swapping the SDK
    = a sibling module under ``agentkit.sdk``, not a builder rewrite.

Naming:
    Lives under ``agentkit.sdk`` (agent-SDK bindings) — NOT to be confused with
    ``agentkit.tools.adapters`` (datasource tool adaptors). The two were both
    called "adapters" historically; the SDK seam was renamed to ``sdk`` to make
    the distinction obvious.

Graceful absence:
    When ``agent_framework`` is not installed (base wheel, or a consumer using a
    different SDK) the builders return ``None`` / ``[]`` exactly as the prior
    GridIQ ``agent.compaction`` / ``agent.middleware`` did — the runtime then
    runs without compaction / SDK tracing rather than failing to boot.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def maf_available() -> bool:
    """Return True when the Microsoft Agent Framework SDK is importable."""
    try:
        import agent_framework  # noqa: F401
    except ImportError:
        return False
    return True


def is_maf_client(client: Any) -> bool:
    """Return True when ``client`` is a Microsoft Agent Framework client.

    Used by :func:`bind_tools` to decide whether to apply the SDK ``@tool``
    binding. The heuristic is the client's defining module's top-level package:
    MAF clients live under ``agent_framework`` (e.g.
    ``agent_framework.azure.AzureAIAgentClient``); the echo/mock stub clients
    live under ``agentkit`` / consumer packages. This keeps the marker-binding
    MAF-specific without the core builder importing the SDK.
    """
    return type(client).__module__.split(".", 1)[0] == "agent_framework"


def bind_tools(tools: Any, client: Any) -> list:
    """Bind agentkit-marked tool callables to the concrete SDK at build time.

    The seam for the ``agentkit.tools.tool`` decorator: a converted tool script
    stamps ``fn.__agentkit_tool__`` and returns the raw callable; this function
    — called from ``agentkit.core.builder.build_agent`` just before
    ``client.as_agent(...)`` — applies the real SDK binding.

    Behaviour:
        - For a MAF ``client``: every callable carrying ``__agentkit_tool__`` is
          wrapped with ``agent_framework.tool(approval_mode=...)`` (lazy import
          of the SDK happens here ONLY, never at ``agentkit.tools`` load), so the
          agent sees an SDK ``@tool``-decorated function identical to the prior
          import-time decoration. Callables/objects without the marker (already
          SDK-decorated tools or ``@server:`` platform-tool objects) pass
          through untouched.
        - For any non-MAF client (echo/mock or a different SDK): the marker is
          ignored and the raw callable is used unchanged.

    Args:
        tools: Iterable of resolved tool callables / platform-tool objects.
        client: The ``AgentClient`` the agent is being built on.

    Returns:
        A new list of tools with MAF-marked callables bound (or the originals
        unchanged for a non-MAF client).
    """
    resolved = list(tools)
    if not is_maf_client(client):
        # Non-MAF client: the SDK ``@tool`` is meaningless here. Pass raw
        # callables through so the marker is a no-op (echo/mock path).
        return resolved

    # Lazy SDK import — only reached when MAF is the active client. Keeps
    # ``agentkit.tools`` and the core builder SDK-free at import time.
    from agent_framework import tool as _maf_tool

    bound: list = []
    for fn in resolved:
        marker = getattr(fn, "__agentkit_tool__", None)
        if marker is None:
            # Already an SDK tool object or a server-tool object — leave it.
            bound.append(fn)
            continue
        approval_mode = marker.get("approval_mode", "never_require")
        bound.append(_maf_tool(approval_mode=approval_mode)(fn))
    return bound



def build_compaction_strategy(token_budget: int, tokenizer: Any) -> Any | None:
    """Build the composed MAF compaction strategy.

    Args:
        token_budget: Total token budget (context window minus response budget).
        tokenizer: Object implementing ``count_tokens`` (``core.Tokenizer``).

    Returns:
        A ``TokenBudgetComposedStrategy`` instance, or ``None`` when the SDK is
        unavailable (caller then attaches no strategy).
    """
    try:
        from agent_framework import (
            TokenBudgetComposedStrategy,
            ToolResultCompactionStrategy,
            TruncationStrategy,
        )
    except ImportError:
        logger.warning("agent_framework compaction classes not available — skipping")
        return None

    strategy = TokenBudgetComposedStrategy(
        strategies=[
            ToolResultCompactionStrategy(),
            TruncationStrategy(max_n=200, compact_to=100, tokenizer=tokenizer),
        ],
        token_budget=token_budget,
        tokenizer=tokenizer,
    )
    logger.info(
        "compaction.created: budget=%d tokens, strategies=[ToolResultCompaction, Truncation]",
        token_budget,
    )
    return strategy


def build_tracing_middleware() -> list:
    """Build the MAF tool-tracing middleware pipeline.

    Returns:
        ``[ToolTracingMiddleware()]`` when the SDK is available, else ``[]``.
        The middleware is purely observational — it never mutates tool
        inputs/outputs; it logs name, duration, and success/failure for every
        tool invocation through the SDK function-invocation pipeline.
    """
    try:
        from agent_framework import (
            FunctionMiddleware,
            FunctionInvocationContext,
        )
    except ImportError:
        logger.warning("agent_framework middleware classes not available — skipping")
        return []

    class ToolTracingMiddleware(FunctionMiddleware):
        """Logs tool invocations with name, duration, and success/failure."""

        async def process(self, context: FunctionInvocationContext, call_next) -> None:
            tool_name = getattr(context.function, "name", "unknown")
            t0 = time.monotonic()
            try:
                await call_next()
                duration_ms = (time.monotonic() - t0) * 1000
                logger.info(
                    "middleware.tool.complete",
                    extra={"tool": tool_name, "duration_ms": round(duration_ms, 1)},
                )
            except Exception as exc:
                duration_ms = (time.monotonic() - t0) * 1000
                logger.warning(
                    "middleware.tool.error",
                    extra={
                        "tool": tool_name,
                        "duration_ms": round(duration_ms, 1),
                        "error": str(exc)[:200],
                    },
                )
                raise

    middlewares: list = [ToolTracingMiddleware()]
    logger.info("middleware.created: %d middleware(s)", len(middlewares))
    return middlewares


__all__ = ["maf_available", "is_maf_client", "bind_tools", "build_compaction_strategy", "build_tracing_middleware"]
