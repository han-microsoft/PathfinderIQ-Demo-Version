"""Step 3 — Delegation tool unit tests (no LLM calls).

Tests that delegate_to_agent:
- Calls load_agent with the correct agent_id
- Runs the specialist agent to completion (stream=False)
- Returns the specialist's response as a JSON tool result
- Handles errors gracefully (returns error JSON, doesn't crash)
- Rejects unknown agent_ids via load_agent's ValueError
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_caches():
    """Reset loader cache and registry client cache between tests."""
    import agents._config as config_mod
    from agents import registry

    # Save and clear
    orig_cache = dict(config_mod._agents_config_cache)
    orig_clients = dict(registry._clients)
    orig_factory = registry._client_factory
    config_mod._agents_config_cache.clear()

    yield

    # Restore
    config_mod._agents_config_cache.clear()
    config_mod._agents_config_cache.update(orig_cache)
    registry._clients = orig_clients
    registry._client_factory = orig_factory


# Flat agents config for mocking
_AGENTS_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "NOCOrchestrator",
        "description": "Orchestrator",
        "instructions": [],
        "tools": ["tools.delegation:delegate_to_agent"],
    },
    "network_investigator": {
        "name": "NetworkInvestigator",
        "description": "Graph expert",
        "instructions": [],
        "tools": ["tools.thinking:thinking"],
    },
}


class TestDelegateToAgentMechanics:
    """delegate_to_agent tool function works with mocked agent."""

    @pytest.mark.asyncio
    @patch("agents._config.load_scenario_yaml", return_value={"agents": _AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    async def test_successful_delegation(self, mock_dir, mock_yaml, tmp_path):
        """Tool builds specialist, runs it, returns response as JSON."""
        from tools.delegation import delegate_to_agent
        from agents import registry

        # Set up mock client and agent
        mock_response = MagicMock()
        mock_response.text = "Found 3 CoreRouters: SYD, MEL, BNE"

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.as_agent.return_value = mock_agent
        registry.configure(lambda: mock_client)

        # Set up paths
        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        # Call the tool
        result = await delegate_to_agent(
            agent_id="network_investigator",
            task="List all CoreRouter nodes",
        )

        # Parse result
        parsed = json.loads(result)
        assert parsed["status"] == "complete"
        assert parsed["agent_id"] == "network_investigator"
        assert "Found 3 CoreRouters" in parsed["response"]
        assert "duration_ms" in parsed

        # Verify agent was built with correct agent_id
        mock_client.as_agent.assert_called_once()
        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "NetworkInvestigator"

        # Verify agent.run was called with stream=False
        mock_agent.run.assert_called_once()
        run_kwargs = mock_agent.run.call_args
        assert run_kwargs.kwargs.get("stream") is False

    @pytest.mark.asyncio
    @patch("agents._config.load_scenario_yaml", return_value={"agents": _AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    async def test_unknown_agent_returns_error(self, mock_dir, mock_yaml, tmp_path):
        """Delegating to a nonexistent agent returns error JSON (no crash)."""
        from tools.delegation import delegate_to_agent
        from agents import registry

        mock_client = MagicMock()
        registry.configure(lambda: mock_client)
        mock_dir.return_value = tmp_path

        result = await delegate_to_agent(
            agent_id="nonexistent_agent",
            task="Do something",
        )

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "not found" in parsed["error"]

    @pytest.mark.asyncio
    async def test_no_client_returns_error(self):
        """Calling without a registered client returns error JSON."""
        from tools.delegation import delegate_to_agent
        import tools.delegation as deleg_mod
        registry._client_factory = None
        registry._clients.clear()

        result = await delegate_to_agent(
            agent_id="network_investigator",
            task="Do something",
        )

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "not registered" in parsed["error"]

    @pytest.mark.asyncio
    @patch("agents._config.load_scenario_yaml", return_value={"agents": _AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    async def test_agent_run_exception_returns_error(self, mock_dir, mock_yaml, tmp_path):
        """If agent.run() throws, the tool returns error JSON (no crash)."""
        from tools.delegation import delegate_to_agent
        from agents import registry

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM API timeout"))

        mock_client = MagicMock()
        mock_client.as_agent.return_value = mock_agent
        registry.configure(lambda: mock_client)

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        result = await delegate_to_agent(
            agent_id="network_investigator",
            task="Investigate",
        )

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "LLM API timeout" in parsed["error"]
        assert parsed["duration_ms"] >= 0


class TestDelegationToolResolution:
    """The delegation tool spec resolves via importlib."""

    def test_importable(self):
        """tools.delegation:delegate_to_agent resolves to a callable."""
        from agents._tools import resolve_tool
        func = resolve_tool("tools.delegation:delegate_to_agent")
        assert callable(func)
