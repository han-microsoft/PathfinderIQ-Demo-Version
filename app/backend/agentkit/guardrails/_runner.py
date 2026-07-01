"""Guardrail execution runner — fail-open chain execution.

Runs a list of guardrails in order. First ``BLOCK`` stops the chain. ``WARN``
results are logged and the chain continues. Exceptions inside a guardrail
are caught and logged — never block the request. The ``guardrail.errors``
OTel counter is incremented on fail-open so dashboards can alert on
persistent failures.

Layering:
    Imports ``agentkit.observability`` (meter) + ``agentkit.guardrails`` types.
    No GridIQ package, no SDK.

Consumed by (GridIQ composition root):
    - ``hosting/fastapi/routers/chat.py`` — input chain before LLM call.
    - ``hosting/fastapi/streaming/service.py`` — output chain post-stream.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agentkit.guardrails import GuardrailResult, GuardrailVerdict
from agentkit.observability import get_meter

if TYPE_CHECKING:
    from agentkit.guardrails import InputGuardrail, OutputGuardrail

logger = logging.getLogger(__name__)

# Counter metric for guardrail failures (fail-open errors).
# Enables operational dashboards to alert when guardrails are consistently erroring.
_meter = get_meter(__name__)
_guardrail_error_counter = _meter.create_counter(
    "guardrail.errors",
    description="Count of guardrail check failures (fail-open errors)",
    unit="1",
)


async def execute_input_guardrails(
    guardrails: list,
    input_text: str,
) -> GuardrailResult | None:
    """Run input guardrails in order. First BLOCK stops the chain.

    Args:
        guardrails: List of InputGuardrail instances.
        input_text: The user's message text to validate.

    Returns:
        None if all pass/warn. GuardrailResult if any BLOCK.
        WARN results are logged but don't stop processing.

    Side effects:
        Logs guardrail.blocked (WARNING), guardrail.warned (INFO),
        guardrail.error (ERROR) for fail-open exceptions.
    """
    for guard in guardrails:
        try:
            result = await guard.check(input_text)
            if result.verdict == GuardrailVerdict.BLOCK:
                logger.warning(
                    "guardrail.blocked",
                    extra={"guardrail": guard.name, "reason": result.reason},
                )
                return result
            if result.verdict == GuardrailVerdict.WARN:
                logger.info(
                    "guardrail.warned",
                    extra={"guardrail": guard.name, "reason": result.reason},
                )
        except Exception as e:
            # Fail-open: guardrail error must never block the request.
            # Emit a counter metric so dashboards can alert on persistent failures.
            logger.error(
                "guardrail.error",
                extra={"guardrail": guard.name, "error": str(e)},
            )
            _guardrail_error_counter.add(1, {"guardrail.name": guard.name})

    return None  # All passed or warned


async def execute_output_guardrails(
    guardrails: list,
    output_text: str,
) -> GuardrailResult | None:
    """Run output guardrails on the completed response text.

    Same semantics as input guardrails, but applied post-streaming.
    BLOCK at this point is advisory only — content has already been
    streamed to the user. The result is logged for audit purposes.

    Args:
        guardrails: List of OutputGuardrail instances.
        output_text: The complete response text.

    Returns:
        The first non-PASS result (WARN or BLOCK), or None if all pass.
    """
    for guard in guardrails:
        try:
            result = await guard.check(output_text)
            if result.verdict in (GuardrailVerdict.BLOCK, GuardrailVerdict.WARN):
                logger.warning(
                    "guardrail.output_flagged",
                    extra={
                        "guardrail": guard.name,
                        "verdict": result.verdict.value,
                        "reason": result.reason,
                    },
                )
                return result
        except Exception as e:
            logger.error(
                "guardrail.error",
                extra={"guardrail": guard.name, "error": str(e)},
            )

    return None
