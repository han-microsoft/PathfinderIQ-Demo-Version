"""TDD tests for agents (AgentRegistry) middleware and context_providers forwarding.

Test approach:
    - Mock client.as_agent() to inspect call kwargs
    - Mock load_scenario_yaml() to return a minimal agents config
    - Mock get_scenario_dir() to return a temp directory
    - Reset the module-level _agents_config_cache between tests
      to prevent cross-test contamination
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """Reset the module-level config cache between tests.

    agents (AgentRegistry) caches parsed scenario YAML in _agents_config_cache.
    Without this reset, tests leak state to each other.
    """
    import agents._config as config_mod
    original_cache = dict(config_mod._agents_config_cache)
    config_mod._agents_config_cache.clear()
    yield
    config_mod._agents_config_cache.clear()
    config_mod._agents_config_cache.update(original_cache)


# Minimal agents config for testing — orchestrator with no specialists
_MINIMAL_AGENTS_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "TestAgent",
        "description": "test",
        "instructions": [],
        "tools": [],
    },
}


class TestLoaderMiddlewareForwarding:
    """TDD: load_agent() forwards middleware= and context_providers= to client.as_agent()."""

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _MINIMAL_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_middleware_forwarded(self, mock_dir, mock_yaml, tmp_path):
        """middleware= kwarg is passed through to client.as_agent()."""
        from agents import registry

        # Create dummy prompts dir so _load_instructions doesn't fail
        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()
        sentinel_mw = [MagicMock()]

        registry.build(None, mock_client, middleware=sentinel_mw)

        mock_client.as_agent.assert_called_once()
        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs.get("middleware") is sentinel_mw

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _MINIMAL_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_context_providers_forwarded(self, mock_dir, mock_yaml, tmp_path):
        """context_providers= kwarg is passed through to client.as_agent()."""
        from agents import registry

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()
        sentinel_cp = [MagicMock()]

        registry.build(None, mock_client, context_providers=sentinel_cp)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs.get("context_providers") is sentinel_cp

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _MINIMAL_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_defaults_none_backward_compat(self, mock_dir, mock_yaml, tmp_path):
        """Without kwargs, middleware and context_providers are explicitly None."""
        from agents import registry

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build(None, mock_client)

        call_kwargs = mock_client.as_agent.call_args
        # Both keys must be PRESENT in the call kwargs (not absent).
        # MagicMock swallows unknown kwargs silently — we need the keys
        # to be explicitly passed so the real SDK receives them.
        assert "middleware" in call_kwargs.kwargs, "middleware= must be explicitly passed to as_agent()"
        assert "context_providers" in call_kwargs.kwargs, "context_providers= must be explicitly passed"
        assert call_kwargs.kwargs["middleware"] is None
        assert call_kwargs.kwargs["context_providers"] is None

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _MINIMAL_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_both_params_forwarded(self, mock_dir, mock_yaml, tmp_path):
        """Both middleware= and context_providers= forwarded in same call."""
        from agents import registry

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()
        sentinel_mw = [MagicMock()]
        sentinel_cp = [MagicMock()]

        registry.build(None, mock_client, middleware=sentinel_mw, context_providers=sentinel_cp)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs.get("middleware") is sentinel_mw
        assert call_kwargs.kwargs.get("context_providers") is sentinel_cp
