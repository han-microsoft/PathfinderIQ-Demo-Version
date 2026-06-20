"""Content safety guardrail — Azure Content Safety API integration.

Checks user messages against Azure Content Safety categories (Hate, SelfHarm,
Sexual, Violence). Configurable severity thresholds. Fail-open: if the API
is unreachable or not configured, returns PASS with reason="not_configured".

Layering:
    Uses raw ``httpx`` + ``azure.identity`` (token only) — no dedicated
    content-safety SDK. Both deps are already core; no extra pip gating needed.
    Imports no GridIQ package.
"""

from __future__ import annotations

import logging
import os

from agentkit.guardrails import GuardrailResult, GuardrailVerdict

logger = logging.getLogger(__name__)


class ContentSafetyGuardrail:
    """Azure Content Safety API integration for input screening.

    Args:
        endpoint: Azure Content Safety endpoint URL. Falls back to
            CONTENT_SAFETY_ENDPOINT env var if not provided.
        threshold: Minimum severity level (0–6) to trigger BLOCK.
            Default 4 = medium-high severity.
    """

    name = "content_safety"

    def __init__(self, endpoint: str = "", threshold: int = 4) -> None:
        self._endpoint = endpoint or os.getenv("CONTENT_SAFETY_ENDPOINT", "")
        self._threshold = threshold
        # Cache the credential and HTTP client across check() calls to avoid:
        #  - Constructing DefaultAzureCredential per call (probes 8 sources)
        #  - TLS handshake per call (new httpx.AsyncClient each time)
        self._cred = None  # Lazy-init on first check()
        self._client = None  # Lazy-init on first check()

    async def check(self, input_text: str) -> GuardrailResult:
        """Check input text against Azure Content Safety.

        Returns PASS if not configured (fail-open for availability).
        Returns BLOCK if any category exceeds the severity threshold.
        """
        if not self._endpoint:
            return GuardrailResult(
                verdict=GuardrailVerdict.PASS,
                guardrail_name=self.name,
                reason="not_configured",
            )

        try:
            import httpx
            import asyncio

            # Lazy-init credential — cached across calls to avoid re-probing
            if self._cred is None:
                from azure.identity import DefaultAzureCredential
                self._cred = DefaultAzureCredential()

            # Acquire token via asyncio.to_thread to avoid blocking the event
            # loop (sync azure.identity SDK, not azure.identity.aio)
            token = await asyncio.to_thread(
                self._cred.get_token,
                "https://cognitiveservices.azure.com/.default",
            )

            # Lazy-init httpx client — reuses connection pool across calls
            if self._client is None:
                self._client = httpx.AsyncClient(timeout=10)

            resp = await self._client.post(
                    f"{self._endpoint}/contentsafety/text:analyze?api-version=2024-09-01",
                    headers={
                        "Authorization": f"Bearer {token.token}",
                        "Content-Type": "application/json",
                    },
                    json={"text": input_text[:10000]},  # API limit
                )
            if resp.status_code != 200:
                logger.warning(
                    "content_safety.api_error: HTTP %d", resp.status_code
                )
                # Fail-open on API error
                return GuardrailResult(
                    verdict=GuardrailVerdict.PASS,
                    guardrail_name=self.name,
                    reason=f"api_error: HTTP {resp.status_code}",
                )

            data = resp.json()
            for category in data.get("categoriesAnalysis", []):
                severity = category.get("severity", 0)
                if severity >= self._threshold:
                    return GuardrailResult(
                        verdict=GuardrailVerdict.BLOCK,
                        guardrail_name=self.name,
                        reason=f"Content flagged: {category.get('category', 'unknown')} (severity {severity})",
                        metadata={
                            "category": category.get("category"),
                            "severity": severity,
                        },
                    )

            return GuardrailResult(
                verdict=GuardrailVerdict.PASS, guardrail_name=self.name
            )

        except Exception as e:
            # Fail-open: Content Safety API down should not block the request.
            # Use a generic reason string — never expose raw exception text
            # (may contain hostnames, ports, or credential errors).
            logger.error("content_safety.error: %s", e)
            return GuardrailResult(
                verdict=GuardrailVerdict.PASS,
                guardrail_name=self.name,
                reason="content_safety_check_unavailable",
            )
