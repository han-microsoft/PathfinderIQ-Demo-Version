"""Tests for app.services.agent_run_state — last-run metadata tracking.

Test file role:
    Validates the agent_run_state module's update and read semantics.
    Ensures the get_last_run() accessor returns a copy (not a mutable reference).
"""

import pytest


class TestAgentRunState:
    """Tests for the last-run metadata state module."""

    def test_initial_state_has_expected_keys(self):
        """The initial state dict has all required keys with zero/empty defaults."""
        from app.services.agent_run_state import get_last_run

        state = get_last_run()
        assert state["model"] == ""
        assert state["input_tokens"] == 0
        assert state["output_tokens"] == 0
        assert state["total_tokens"] == 0
        assert state["duration_ms"] == 0
        assert state["tool_calls"] == 0
        assert state["thread_id"] == ""

    def test_update_merges_fields(self):
        """update_last_run merges provided fields into the state."""
        from app.services.agent_run_state import get_last_run, update_last_run

        update_last_run(model="gpt-5.2", total_tokens=1000, duration_ms=350)
        state = get_last_run()
        assert state["model"] == "gpt-5.2"
        assert state["total_tokens"] == 1000
        assert state["duration_ms"] == 350

    def test_update_preserves_unmentioned_fields(self):
        """Fields not mentioned in the update call retain their current values."""
        from app.services.agent_run_state import get_last_run, update_last_run

        update_last_run(model="test-model")
        update_last_run(tool_calls=5)
        state = get_last_run()
        # model should still be "test-model" from the first call
        assert state["model"] == "test-model"
        assert state["tool_calls"] == 5

    def test_get_returns_copy_not_reference(self):
        """get_last_run returns a copy — mutating it doesn't affect internal state."""
        from app.services.agent_run_state import get_last_run

        state = get_last_run()
        state["model"] = "mutated-externally"
        # The internal state should be unchanged
        assert get_last_run()["model"] != "mutated-externally"
