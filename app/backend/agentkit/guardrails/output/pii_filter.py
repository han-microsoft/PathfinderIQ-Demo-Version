"""PII filter guardrail — regex-based PII detection in LLM output.

Detects common PII patterns: email addresses, phone numbers, SSNs, and
credit card numbers. IPv4 addresses are intentionally excluded — they are
expected in many operational / log contexts and are routinely not PII there.

The pattern list is configurable per-instance to support deployment-specific
tuning via the consumer's guardrail configuration.

Returns WARN (not BLOCK) — content has already been streamed to the user
by the time output guardrails run. The warning is logged for audit trails.

Future: integrate with Azure AI Language PII detection endpoint for
ML-based detection with entity-level redaction.
"""

from __future__ import annotations

import re
from typing import Any

from agentkit.guardrails import GuardrailResult, GuardrailVerdict

# Default PII patterns — intentionally excludes IPv4 (expected in operational logs)
_DEFAULT_PATTERNS: dict[str, str] = {
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
}


class PIIFilterGuardrail:
    """Detect PII in LLM output using regex patterns.

    Args:
        patterns: Custom pattern dict to override defaults. Each key is a
            PII type name, each value is a regex pattern string.
    """

    name = "pii_filter"

    def __init__(self, patterns: dict[str, str] | None = None) -> None:
        self._patterns = patterns or _DEFAULT_PATTERNS

    async def check(self, output_text: str) -> GuardrailResult:
        """Scan output text for PII patterns.

        Returns WARN on any match (with list of PII types found).
        Returns PASS if clean.
        """
        findings: list[str] = []
        for pii_type, pattern in self._patterns.items():
            if re.search(pattern, output_text):
                findings.append(pii_type)

        if findings:
            return GuardrailResult(
                verdict=GuardrailVerdict.WARN,
                guardrail_name=self.name,
                reason=f"PII detected: {', '.join(findings)}",
                metadata={"pii_types": findings},
            )

        return GuardrailResult(
            verdict=GuardrailVerdict.PASS, guardrail_name=self.name
        )
