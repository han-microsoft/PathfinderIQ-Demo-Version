"""Input length guardrail — token-based length check.

Blocks user messages that exceed a configurable token limit. Uses the same
tiktoken encoder as the context window (``_context.py:count_tokens``).

Note: Character-based length checking is intentionally omitted — Pydantic's
``max_length=100_000`` on ChatRequest already handles that at the API boundary.
This guardrail adds TOKEN-based limits, which Pydantic cannot enforce.
"""

from __future__ import annotations

from app.guardrails import GuardrailResult, GuardrailVerdict


class InputLengthGuardrail:
    """Check user input token count against a configurable limit.

    Args:
        max_tokens: Maximum allowed tokens. 0 = no limit (passes all).
    """

    name = "input_length"

    def __init__(self, max_tokens: int = 0) -> None:
        self._max_tokens = max_tokens

    async def check(self, input_text: str) -> GuardrailResult:
        """Check input text against the token limit.

        Returns PASS if max_tokens is 0 (disabled) or input is within limit.
        Returns BLOCK if input exceeds the token limit.
        """
        if not self._max_tokens:
            return GuardrailResult(
                verdict=GuardrailVerdict.PASS, guardrail_name=self.name
            )

        from app.services.conversation._context import count_tokens

        tokens = count_tokens(input_text)
        if tokens > self._max_tokens:
            return GuardrailResult(
                verdict=GuardrailVerdict.BLOCK,
                guardrail_name=self.name,
                reason=f"Input exceeds {self._max_tokens} tokens ({tokens} tokens sent)",
            )

        return GuardrailResult(
            verdict=GuardrailVerdict.PASS, guardrail_name=self.name
        )
