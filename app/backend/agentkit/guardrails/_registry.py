"""Guardrail registry — name → class resolution from agent configuration.

Maps the string names used in ``agents.<id>.input_guardrails`` /
``output_guardrails`` to their implementing classes. ``resolve_guardrails()``
instantiates them. Unknown names are logged and skipped — never raise.

Consumed by (GridIQ composition root):
    - ``app/_startup.py:initialize_guardrails``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Lazy imports inside resolve_guardrails() to avoid circular imports
# and unnecessary module loading when guardrails are disabled.


def resolve_guardrails(names: list[str]) -> list:
    """Resolve guardrail names to instantiated guardrail objects.

    Unknown names are logged and skipped — they do not crash startup.

    Args:
        names: List of guardrail name strings from the agent configuration.

    Returns:
        List of instantiated guardrail objects (InputGuardrail or OutputGuardrail).
    """
    # Import registry entries lazily
    from agentkit.guardrails.input.content_safety import ContentSafetyGuardrail
    from agentkit.guardrails.input.input_length import InputLengthGuardrail
    from agentkit.guardrails.input.prompt_shield import PromptShieldGuardrail
    from agentkit.guardrails.output.pii_filter import PIIFilterGuardrail

    _REGISTRY: dict[str, type] = {
        "content_safety": ContentSafetyGuardrail,
        "input_length": InputLengthGuardrail,
        "prompt_shield": PromptShieldGuardrail,
        "pii_filter": PIIFilterGuardrail,
    }

    instances = []
    for name in names:
        cls = _REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown guardrail: '%s' — skipping", name)
            continue
        instances.append(cls())
    return instances
