"""Compaction strategy factory (K7) — token budget via settings, SDK via adapter.

Module role:
    Provides ``TiktokenAdapter`` (implements ``core.Tokenizer``) and a factory
    that builds a composed compaction strategy. The concrete SDK strategy
    classes live in ``agentkit.sdk.maf_client`` (isolate-SDK-quirks); this
    module reads the token budget from the registered settings and delegates
    construction to the adapter.

Layering:
    Imports ``agentkit.config`` (settings accessor), ``agentkit.tokens`` (token
    counter), and ``agentkit.sdk.maf_client`` (lazy, at call time). No
    GridIQ package. Was ``agent/compaction.py``.
"""

from __future__ import annotations

import logging

from agentkit.config import get_settings
from agentkit.tokens import count_tokens

logger = logging.getLogger(__name__)


class TiktokenAdapter:
    """Adapts tiktoken to the SDK's TokenizerProtocol (``core.Tokenizer``).

    Thread-safe: token counting delegates to the shared ``agentkit.tokens``
    helper so the codebase has one tokenizer initialization path.
    """

    def __init__(self) -> None:
        return None

    def count_tokens(self, text: str) -> int:
        """Count tokens in a string using tiktoken.

        Args:
            text: The input string to tokenize.

        Returns:
            Non-negative integer token count.
        """
        return count_tokens(text)


def create_compaction_strategy():
    """Create a composed compaction strategy matching prior behaviour.

    Reads ``max_context_tokens`` / ``max_response_tokens`` from the registered
    settings, then asks the MAF adapter to build the composed strategy
    (ToolResultCompaction + Truncation under the token budget).

    Returns:
        A CompactionStrategy instance, or ``None`` if the SDK is unavailable.
    """
    settings = get_settings()
    budget = settings.max_context_tokens - settings.max_response_tokens
    tokenizer = TiktokenAdapter()

    from agentkit.sdk.maf_client import build_compaction_strategy

    return build_compaction_strategy(budget, tokenizer)
