"""Token cost estimation — tests for estimate_cost().

Phase 1.2: Cost estimation utility that maps (model, prompt_tokens,
completion_tokens) to an estimated USD cost using a static pricing table.

Test strategy:
    - Known models return a float cost
    - Unknown models return None (no misleading zeros)
    - Zero tokens return 0.0 cost for known models
    - Negative tokens are handled gracefully
    - Return value is rounded to avoid floating-point noise
"""

from __future__ import annotations


class TestEstimateCost:
    """estimate_cost() maps model + tokens to USD cost."""

    def _estimate(self, model: str, prompt: int, completion: int):
        from app.llmops._cost import estimate_cost
        return estimate_cost(model, prompt, completion)

    def test_known_model_returns_float(self):
        """Known model with non-zero tokens returns a float cost."""
        cost = self._estimate("gpt-4.1", 1000, 500)
        assert isinstance(cost, float)
        assert cost > 0

    def test_unknown_model_returns_none(self):
        """Unknown model returns None — no misleading zeros."""
        cost = self._estimate("unknown-model-xyz", 1000, 500)
        assert cost is None

    def test_zero_tokens_returns_zero(self):
        """Known model with zero tokens returns 0.0."""
        cost = self._estimate("gpt-4.1", 0, 0)
        assert cost == 0.0

    def test_prompt_only(self):
        """Cost with only prompt tokens (no completion)."""
        cost = self._estimate("gpt-4.1", 1_000_000, 0)
        assert cost is not None
        # gpt-4.1 input = $2.00 per 1M tokens
        assert abs(cost - 2.0) < 0.01

    def test_completion_only(self):
        """Cost with only completion tokens (no prompt)."""
        cost = self._estimate("gpt-4.1", 0, 1_000_000)
        assert cost is not None
        # gpt-4.1 output = $8.00 per 1M tokens
        assert abs(cost - 8.0) < 0.01

    def test_no_floating_point_noise(self):
        """Result should not have excessive decimal places."""
        cost = self._estimate("gpt-4.1", 100, 50)
        assert cost is not None
        # str representation should not have more than 6 decimal places
        cost_str = f"{cost:.10f}".rstrip("0")
        decimal_places = len(cost_str.split(".")[1]) if "." in cost_str else 0
        assert decimal_places <= 6

    def test_echo_model_returns_none(self):
        """'echo' model is not in the pricing table — returns None."""
        assert self._estimate("echo", 100, 100) is None

    def test_mock_model_returns_none(self):
        """'mock' model is not in the pricing table — returns None."""
        assert self._estimate("mock", 100, 100) is None

    def test_empty_model_returns_none(self):
        """Empty model string returns None."""
        assert self._estimate("", 100, 100) is None
