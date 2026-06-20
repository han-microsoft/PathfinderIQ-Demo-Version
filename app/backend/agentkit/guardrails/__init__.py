"""Guardrail framework — input/output validation for LLM interactions.

Defines the ``InputGuardrail`` / ``OutputGuardrail`` Protocols,
``GuardrailVerdict``, and ``GuardrailResult``. Concrete checks live in
``input/`` and ``output/``. Provider-agnostic; fail-open by contract.

Layering:
    Pure ``pydantic`` + stdlib at this level. Imports no GridIQ package and no
    SDK. Lifted from GridIQ ``ops.guardrails`` during the Inc11b cleanliness
    pass — generic AI-safety primitives, not domain content.

Public API:
    from agentkit.guardrails import GuardrailVerdict, GuardrailResult
    from agentkit.guardrails._runner import execute_input_guardrails, execute_output_guardrails
    from agentkit.guardrails._registry import resolve_guardrails

Consumed by (GridIQ composition root):
    - ``app/_startup.py:initialize_guardrails`` — resolves names from ``control/agent_config.yaml``.
    - ``hosting/fastapi/deps.py:get_input_guardrails`` / ``get_output_guardrails`` — DI.
    - ``hosting/fastapi/routers/chat.py`` — input chain before LLM call.
    - ``hosting/fastapi/streaming/service.py`` — output chain post-stream.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class GuardrailVerdict(str, Enum):
    """Result of a guardrail check.

    PASS:  Content is acceptable — proceed.
    WARN:  Content is borderline — proceed but log.
    BLOCK: Content is unacceptable — stop processing.
    """

    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class GuardrailResult(BaseModel):
    """Result of a single guardrail check.

    Attributes:
        verdict: PASS, WARN, or BLOCK.
        guardrail_name: Name of the guardrail that produced this result.
        reason: Human-readable explanation (displayed to user on BLOCK).
        metadata: Arbitrary detail (e.g., PII types found, severity scores).
    """

    verdict: GuardrailVerdict
    guardrail_name: str
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class InputGuardrail(Protocol):
    """Protocol for input validation guardrails.

    Checks user input before it reaches the LLM.
    Implementations must be async and must not raise on transient failures
    (fail-open — return PASS with reason="error: ..." instead).
    """

    name: str

    async def check(self, input_text: str) -> GuardrailResult: ...


@runtime_checkable
class OutputGuardrail(Protocol):
    """Protocol for output validation guardrails.

    Checks LLM output after streaming completes (before persistence).
    WARN results are logged but don't block. BLOCK results are logged
    but content has already been streamed to the user — the block is
    advisory (logged for audit, not enforced on already-sent content).
    """

    name: str

    async def check(self, output_text: str) -> GuardrailResult: ...


__all__ = [
    "GuardrailVerdict",
    "GuardrailResult",
    "InputGuardrail",
    "OutputGuardrail",
]
