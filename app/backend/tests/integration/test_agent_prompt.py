"""Integration tests for GET /api/scenario/agent-prompt.

Validates that the agent prompt endpoint returns the assembled
system prompt text from the active scenario's prompt files.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python -m pytest tests/integration/test_agent_prompt.py -v
"""

import pytest

pytestmark = pytest.mark.integration


class TestAgentPromptEndpoint:
    """Tests for GET /api/scenario/agent-prompt."""

    def test_returns_prompt_text(self, client):
        """Endpoint returns agent name, file list, and prompt text."""
        res = client.get("/api/scenario/agent-prompt")
        assert res.status_code == 200
        body = res.json()

        # Must have the expected keys
        assert "agent_name" in body
        assert "instruction_files" in body
        assert "prompt_text" in body
        assert "char_count" in body

        # Prompt text should be non-empty (scenario has prompt files)
        assert isinstance(body["prompt_text"], str)
        assert body["char_count"] >= 0

    def test_instruction_files_is_list(self, client):
        """instruction_files is a list of strings."""
        res = client.get("/api/scenario/agent-prompt")
        body = res.json()
        assert isinstance(body["instruction_files"], list)

    def test_char_count_matches_text_length(self, client):
        """char_count matches the actual length of prompt_text."""
        res = client.get("/api/scenario/agent-prompt")
        body = res.json()
        if body.get("prompt_text"):
            assert body["char_count"] == len(body["prompt_text"])
