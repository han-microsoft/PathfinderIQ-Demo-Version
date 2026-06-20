"""Input length guardrail — token-based length check.

Blocks user messages that exceed a configurable token limit. Uses
``agentkit.tokens.count_tokens`` (the same tiktoken encoder applied to
the LLM context window). Character-based length is already bounded at
the API boundary by Pydantic ``max_length`` on the chat request schema;
this guardrail adds the token-based limit Pydantic cannot enforce.
"""

from __future__ import annotations

from agentkit.guardrails import GuardrailResult, GuardrailVerdict


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

        from agentkit.tokens import count_tokens

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
