"""Guardrail framework — tests for protocol, runner, and implementations.

Phase 1.6: Input/Output guardrail protocol, fail-open runner, and
concrete guardrail implementations (content safety, input length,
prompt shield, PII filter).
"""

from __future__ import annotations

import pytest


# ── Protocol & Enum ──────────────────────────────────────────────────────────


class TestGuardrailVerdict:
    """GuardrailVerdict enum structure."""

    def test_expected_values(self):
        from app.guardrails import GuardrailVerdict
        assert {v.value for v in GuardrailVerdict} == {"pass", "warn", "block"}


class TestGuardrailResult:
    """GuardrailResult data model."""

    def test_creation(self):
        from app.guardrails import GuardrailResult, GuardrailVerdict
        r = GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name="test")
        assert r.verdict == GuardrailVerdict.PASS
        assert r.guardrail_name == "test"
        assert r.reason == ""
        assert r.metadata == {}

    def test_with_metadata(self):
        from app.guardrails import GuardrailResult, GuardrailVerdict
        r = GuardrailResult(
            verdict=GuardrailVerdict.BLOCK,
            guardrail_name="content_safety",
            reason="Violence detected",
            metadata={"category": "Violence", "severity": 6},
        )
        assert r.metadata["category"] == "Violence"


# ── Runner ───────────────────────────────────────────────────────────────────


class TestExecuteInputGuardrails:
    """execute_input_guardrails() — chain execution with fail-open."""

    async def test_empty_list_returns_none(self):
        """No guardrails → None (all pass)."""
        from app.guardrails._runner import execute_input_guardrails
        result = await execute_input_guardrails([], "hello")
        assert result is None

    async def test_single_pass(self):
        """One passing guardrail → None."""
        from app.guardrails import GuardrailResult, GuardrailVerdict
        from app.guardrails._runner import execute_input_guardrails

        class PassGuard:
            name = "always_pass"
            async def check(self, text):
                return GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name=self.name)

        result = await execute_input_guardrails([PassGuard()], "hello")
        assert result is None

    async def test_block_stops_chain(self):
        """First BLOCK stops — subsequent guardrails don't run."""
        from app.guardrails import GuardrailResult, GuardrailVerdict
        from app.guardrails._runner import execute_input_guardrails

        call_order = []

        class BlockGuard:
            name = "blocker"
            async def check(self, text):
                call_order.append("blocker")
                return GuardrailResult(verdict=GuardrailVerdict.BLOCK, guardrail_name=self.name, reason="blocked")

        class PassGuard:
            name = "after_blocker"
            async def check(self, text):
                call_order.append("after_blocker")
                return GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name=self.name)

        result = await execute_input_guardrails([BlockGuard(), PassGuard()], "hello")
        assert result is not None
        assert result.verdict == GuardrailVerdict.BLOCK
        assert call_order == ["blocker"]  # Second guard never ran

    async def test_warn_continues(self):
        """WARN is logged but chain continues — returns None."""
        from app.guardrails import GuardrailResult, GuardrailVerdict
        from app.guardrails._runner import execute_input_guardrails

        class WarnGuard:
            name = "warner"
            async def check(self, text):
                return GuardrailResult(verdict=GuardrailVerdict.WARN, guardrail_name=self.name, reason="borderline")

        result = await execute_input_guardrails([WarnGuard()], "hello")
        assert result is None  # WARN does not block

    async def test_fail_open_on_exception(self):
        """Guardrail that raises → fail open, chain continues."""
        from app.guardrails import GuardrailResult, GuardrailVerdict
        from app.guardrails._runner import execute_input_guardrails

        class CrashGuard:
            name = "crasher"
            async def check(self, text):
                raise RuntimeError("Guardrail API down")

        class PassGuard:
            name = "after_crash"
            async def check(self, text):
                return GuardrailResult(verdict=GuardrailVerdict.PASS, guardrail_name=self.name)

        # Must not raise — fail-open
        result = await execute_input_guardrails([CrashGuard(), PassGuard()], "hello")
        assert result is None


# ── Input Length Guardrail ───────────────────────────────────────────────────


class TestInputLengthGuardrail:
    """InputLengthGuardrail — token-based length check."""

    async def test_short_input_passes(self):
        from app.guardrails.input.input_length import InputLengthGuardrail
        from app.guardrails import GuardrailVerdict

        guard = InputLengthGuardrail(max_tokens=1000)
        result = await guard.check("Hello world")
        assert result.verdict == GuardrailVerdict.PASS

    async def test_long_input_blocked(self):
        from app.guardrails.input.input_length import InputLengthGuardrail
        from app.guardrails import GuardrailVerdict

        guard = InputLengthGuardrail(max_tokens=5)
        # "This is a sentence with many tokens" should exceed 5 tokens
        result = await guard.check("This is a sentence with many tokens that definitely exceeds five tokens")
        assert result.verdict == GuardrailVerdict.BLOCK

    async def test_zero_max_tokens_passes_all(self):
        from app.guardrails.input.input_length import InputLengthGuardrail
        from app.guardrails import GuardrailVerdict

        guard = InputLengthGuardrail(max_tokens=0)
        result = await guard.check("Any input")
        assert result.verdict == GuardrailVerdict.PASS


# ── PII Filter Guardrail ────────────────────────────────────────────────────


class TestPIIFilterGuardrail:
    """PIIFilterGuardrail — regex-based PII detection."""

    async def test_clean_text_passes(self):
        from app.guardrails.output.pii_filter import PIIFilterGuardrail
        from app.guardrails import GuardrailVerdict

        guard = PIIFilterGuardrail()
        result = await guard.check("The router is operating normally at 98% utilization.")
        assert result.verdict == GuardrailVerdict.PASS

    async def test_email_detected(self):
        from app.guardrails.output.pii_filter import PIIFilterGuardrail
        from app.guardrails import GuardrailVerdict

        guard = PIIFilterGuardrail()
        result = await guard.check("Contact the engineer at admin@corp.com for help.")
        assert result.verdict == GuardrailVerdict.WARN
        assert "email" in result.metadata.get("pii_types", [])

    async def test_ssn_detected(self):
        from app.guardrails.output.pii_filter import PIIFilterGuardrail
        from app.guardrails import GuardrailVerdict

        guard = PIIFilterGuardrail()
        result = await guard.check("SSN is 123-45-6789")
        assert result.verdict == GuardrailVerdict.WARN

    async def test_ip_address_not_flagged(self):
        """IPv4 addresses are NOT PII in network ops domain — not in default patterns."""
        from app.guardrails.output.pii_filter import PIIFilterGuardrail
        from app.guardrails import GuardrailVerdict

        guard = PIIFilterGuardrail()
        result = await guard.check("Router at 10.0.1.1 is responding.")
        assert result.verdict == GuardrailVerdict.PASS


# ── Registry ─────────────────────────────────────────────────────────────────


class TestGuardrailRegistry:
    """resolve_guardrails() — name → instance resolution."""

    def test_resolve_known_guardrail(self):
        from app.guardrails._registry import resolve_guardrails
        guards = resolve_guardrails(["input_length"])
        assert len(guards) == 1
        assert guards[0].name == "input_length"

    def test_resolve_unknown_skips(self):
        from app.guardrails._registry import resolve_guardrails
        guards = resolve_guardrails(["nonexistent_guardrail"])
        assert len(guards) == 0

    def test_resolve_empty_list(self):
        from app.guardrails._registry import resolve_guardrails
        guards = resolve_guardrails([])
        assert guards == []
