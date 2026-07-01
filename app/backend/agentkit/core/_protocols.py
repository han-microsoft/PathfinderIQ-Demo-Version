"""Agent-core SDK seam protocols — structural types, zero concrete SDK binding.

Module role:
    Names the structural contracts the agent runtime depends on so that the
    concrete SDK (Microsoft Agent Framework today) is isolated to one adapter
    file (``agentkit.sdk.maf_client``). ``builder.build_agent`` accepts any
    object satisfying ``AgentClient``; ``compaction.TiktokenAdapter`` satisfies
    ``Tokenizer``. Swapping the SDK = swap the adapter, not the core runtime.

Layering:
    Pure stdlib + typing only. Imports no GridIQ package and no SDK at import
    time (§3.3 of genericize/TIER1_EXTRACTION_PLAN.md).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentClient(Protocol):
    """Structural contract for the SDK client the builder constructs agents on.

    The only method ``builder.build_agent`` invokes is ``as_agent(...)``; the
    concrete client (e.g. ``agent_framework.azure.AzureAIAgentClient``) is built
    by the consumer's composition root and injected into ``AgentRegistry``. The
    builder never imports the SDK class — it only calls this method.
    """

    def as_agent(
        self,
        *,
        name: str,
        description: str,
        instructions: str,
        tools: Any | None = ...,
        default_options: dict[str, Any] | None = ...,
        middleware: Any | None = ...,
        context_providers: Any | None = ...,
    ) -> Any:
        """Construct and return an SDK Agent object."""
        ...


@runtime_checkable
class Tokenizer(Protocol):
    """Structural contract for a token counter consumed by compaction.

    Matches the SDK ``TokenizerProtocol`` surface used by the composed
    compaction strategy. ``compaction.TiktokenAdapter`` implements it.
    """

    def count_tokens(self, text: str) -> int:
        """Return a non-negative token count for ``text``."""
        ...


__all__ = ["AgentClient", "Tokenizer"]
