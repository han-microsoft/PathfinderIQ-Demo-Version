"""Token cost estimation — model pricing lookup.

Module role:
    Maps (model_name, prompt_tokens, completion_tokens) to an estimated USD cost.
    Uses a static pricing table with approximate public rates. The table is NOT
    billing-accurate — it provides order-of-magnitude cost visibility for
    operational dashboards and LLMOps traces.

    Returns ``None`` for unknown models (not 0.0) to avoid misleading data.
    Dev providers (echo, mock) have no pricing entry and correctly return None.

Key collaborators:
    - ``app.models.StreamMetadata``     — embeds ``estimated_cost_usd``
    - ``app.services.llm.agent``        — calls at METADATA emission (Phase 4)
    - ``app.services.llm.openai``       — calls at METADATA emission
    - ``app.llmops._protocol.LLMTrace`` — includes cost in trace records (Phase 1.1)

Dependents:
    Called by: LLM provider METADATA emission code, LLMOps trace builder.

Maintenance:
    Add new models to ``_PRICING`` as they become available. Rates are
    approximate USD per 1 million tokens (input, output).
"""

from __future__ import annotations

# Pricing table — approximate USD per 1M tokens: (input_per_1M, output_per_1M)
# Source: public model pricing pages. Updated manually.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.2": (3.00, 12.00),
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
    """Estimate USD cost for a single LLM invocation.

    Args:
        model: Model deployment name (e.g., ``"gpt-4.1"``, ``"gpt-5.2"``).
        prompt_tokens: Number of input tokens consumed.
        completion_tokens: Number of output tokens generated.

    Returns:
        Estimated cost in USD, rounded to 6 decimal places. Returns ``None``
        if the model is not in the pricing table (unknown models produce no
        misleading zero-cost entries).

    Side effects:
        None — pure function.
    """
    rates = _PRICING.get(model)
    if rates is None:
        return None
    # Compute cost: (tokens * rate_per_million) / 1_000_000
    cost = (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000
    return round(cost, 6)
