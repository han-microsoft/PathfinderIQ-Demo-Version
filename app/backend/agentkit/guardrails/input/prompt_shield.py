"""Prompt shield guardrail — prompt injection detection.

Detects common prompt injection patterns in user input using regex-based
pattern matching. A lightweight first line of defence — upgrade to Azure
AI Content Safety Prompt Shields API for production-grade detection.
"""

from __future__ import annotations

import re

from agentkit.guardrails import GuardrailResult, GuardrailVerdict

# Patterns indicating prompt injection attempts.
# Each pattern is compiled once at import time.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your\s+instructions?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|your)\s+(instructions?|directives?|rules?)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),  # XML injection attempt
]


class PromptShieldGuardrail:
    """Detect prompt injection attempts in user input.

    Uses regex patterns for common injection vectors. Returns BLOCK
    when a pattern matches. This is intentionally conservative — false
    positives on legitimate queries containing these phrases are acceptable
    because the alternative (prompt injection succeeding) is worse.

    Future: integrate with Azure AI Content Safety Prompt Shields API
    for ML-based detection with lower false positive rates.
    """

    name = "prompt_shield"

    async def check(self, input_text: str) -> GuardrailResult:
        """Scan input text for prompt injection patterns.

        Returns BLOCK on the first pattern match.
        Returns PASS if no patterns match.
        """
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(input_text):
                return GuardrailResult(
                    verdict=GuardrailVerdict.BLOCK,
                    guardrail_name=self.name,
                    reason="Input appears to contain a prompt injection attempt.",
                    metadata={"matched_pattern": pattern.pattern},
                )

        return GuardrailResult(
            verdict=GuardrailVerdict.PASS, guardrail_name=self.name
        )
