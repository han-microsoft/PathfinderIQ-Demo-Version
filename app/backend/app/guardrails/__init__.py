"""Guardrail framework — input/output validation for LLM interactions.

Package role:
    Defines the guardrail protocol (InputGuardrail, OutputGuardrail),
    result types (GuardrailVerdict, GuardrailResult), and the execution
    runner. Concrete implementations live in ``input/`` and ``output/``
    subpackages.

    Guardrails are provider-agnostic library code. At the HTTP layer
    (chat.py), they validate user input before the LLM call and LLM
    output after streaming completes. At the SDK middleware layer (future),
    the same guardrail instances are invoked via AgentGuardrailMiddleware.

Public API:
    from app.guardrails import GuardrailVerdict, GuardrailResult
    from app.guardrails._runner import execute_input_guardrails
    from app.guardrails._registry import resolve_guardrails

Key collaborators:
    - ``app.routers.chat``       — executes guardrails before/after LLM call
    - ``app.deps``               — injects guardrail lists via Depends()
    - ``agents`` (AgentRegistry) — loads guardrail config from scenario.yaml
    - ``scenario.yaml``          — declares which guardrails are active

Dependents:
    The protocol and runner are consumed by chat.py and (future)
    AgentGuardrailMiddleware.
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
