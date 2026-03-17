"""Flat agent config tests — scenario.yaml defines agents as flat peers.

Tests that the flat config format is correctly parsed, load_agent() resolves
agents by ID, registry.list_definitions() returns metadata, and error handling
works for missing agents.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """Reset the module-level config cache between tests."""
    import agents._config as config_mod
    original_cache = dict(config_mod._agents_config_cache)
    config_mod._agents_config_cache.clear()
    yield
    config_mod._agents_config_cache.clear()
    config_mod._agents_config_cache.update(original_cache)


# Multi-agent flat config matching the telecom-playground scenario structure
_FLAT_AGENTS_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "NOCOrchestrator",
        "description": "Network operations orchestrator.",
        "instructions": [],
        "tools": ["tools.thinking:thinking"],
    },
    "network_investigator": {
        "name": "NetworkInvestigator",
        "description": "Graph topology expert.",
        "instructions": [],
        "tools": ["tools.thinking:thinking", "tools.graph_explorer:query_graph"],
    },
    "knowledge_analyst": {
        "name": "KnowledgeAnalyst",
        "description": "Runbook and ticket search.",
        "instructions": [],
        "tools": ["tools.thinking:thinking"],
    },
}


class TestListAgentDefinitions:
    """registry.list_definitions() returns metadata for all agents."""

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    def test_returns_all_agents(self, mock_yaml):
        """All non-reserved entries returned."""
        from agents import registry
        defs = registry.list_definitions()
        ids = [d["id"] for d in defs]
        assert "orchestrator" in ids
        assert "network_investigator" in ids
        assert "knowledge_analyst" in ids
        # Reserved key 'default' must NOT appear as an agent
        assert "default" not in ids
        assert len(defs) == 3

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    def test_default_agent_flagged(self, mock_yaml):
        """The default agent has is_default=True, others False."""
        from agents import registry
        defs = registry.list_definitions()
        defaults = [d for d in defs if d["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "orchestrator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    def test_metadata_shape(self, mock_yaml):
        """Each entry has id, name, description, tool_count, is_default."""
        from agents import registry
        defs = registry.list_definitions()
        for d in defs:
            assert "id" in d
            assert "name" in d
            assert "description" in d
            assert "tool_count" in d
            assert "is_default" in d
            assert isinstance(d["tool_count"], int)

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    def test_tool_count_correct(self, mock_yaml):
        """tool_count matches the length of the tools list."""
        from agents import registry
        defs = registry.list_definitions()
        inv = next(d for d in defs if d["id"] == "network_investigator")
        assert inv["tool_count"] == 2  # thinking + query_graph


class TestLoadAgentById:
    """load_agent() builds agents by ID from the flat config."""

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_default_agent_loaded(self, mock_dir, mock_yaml, tmp_path):
        """load_agent() without agent_id loads the default agent."""
        from agents import registry

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build(None, mock_client)

        # Default is 'orchestrator' — name should be NOCOrchestrator
        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "NOCOrchestrator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_specific_agent_loaded(self, mock_dir, mock_yaml, tmp_path):
        """load_agent(agent_id='network_investigator') loads that agent."""
        from agents import registry

        prompts_dir = tmp_path / "data" / "prompts"
        prompts_dir.mkdir(parents=True)
        mock_dir.return_value = tmp_path

        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("network_investigator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "NetworkInvestigator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _FLAT_AGENTS_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_nonexistent_agent_raises(self, mock_dir, mock_yaml, tmp_path):
        """load_agent(agent_id='bogus') raises ValueError."""
        from agents import registry

        mock_dir.return_value = tmp_path

        mock_client = MagicMock()

        with pytest.raises(ValueError, match="not found"):
            registry.build("bogus", mock_client)

    @patch("agents._config.load_scenario_yaml", return_value={"agents": {"default": "x"}})
    @patch("app.scenario.get_scenario_dir")
    def test_default_points_to_missing_agent(self, mock_dir, mock_yaml, tmp_path):
        """ValueError when default key points to a nonexistent agent."""
        from agents import registry

        mock_dir.return_value = tmp_path
        mock_client = MagicMock()

        with pytest.raises(ValueError, match="not found"):
            registry.build(None, mock_client)


class TestIterAgentEntries:
    """iter_agents() skips reserved keys."""

    def test_skips_default_key(self):
        """'default' key is not returned as an agent entry."""
        from agents._config import iter_agents
        config = {"default": "a", "a": {"name": "A"}, "b": {"name": "B"}}
        entries = iter_agents(config)
        ids = [e[0] for e in entries]
        assert "default" not in ids
        assert "a" in ids
        assert "b" in ids

    def test_skips_stale_mode_key(self):
        """'mode' key is ignored as a non-dict scalar (stale YAML compat)."""
        from agents._config import iter_agents
        config = {"mode": "multi", "default": "a", "a": {"name": "A"}}
        entries = iter_agents(config)
        ids = [e[0] for e in entries]
        assert "mode" not in ids
        assert "default" not in ids

    def test_skips_non_dict_values(self):
        """Non-dict entries are skipped (e.g. scalar values)."""
        from agents._config import iter_agents
        config = {"default": "a", "a": {"name": "A"}, "some_string": "hello"}
        entries = iter_agents(config)
        ids = [e[0] for e in entries]
        assert "some_string" not in ids


class TestScenarioAgentToolResolution:
    """All tool specs from the real scenario.yaml resolve to callables."""

    def test_orchestrator_tools_resolve(self):
        """All orchestrator tool specs resolve."""
        from agents._tools import resolve_tool
        specs = [
            "tools.network:reroute_traffic",
            "tools.network:set_link_status",
            "tools.dispatch:dispatch_field_engineer",
            "tools.dispatch:call_engineer",
            "tools.incidents:create_incident_ticket",
            "tools.incidents:update_advisory",
            "tools.email:send_incident_report",
            "tools.thinking:thinking",
        ]
        for spec in specs:
            assert callable(resolve_tool(spec)), f"Tool '{spec}' not callable"

    def test_network_investigator_tools_resolve(self):
        """NetworkInvestigator tool specs resolve."""
        from agents._tools import resolve_tool
        specs = [
            "tools.graph_explorer:query_graph",
            "tools.telemetry:query_telemetry",
            "tools.thinking:thinking",
        ]
        for spec in specs:
            assert callable(resolve_tool(spec))

    def test_knowledge_analyst_tools_resolve(self):
        """KnowledgeAnalyst tool specs resolve."""
        from agents._tools import resolve_tool
        specs = [
            "tools.search:search_runbooks",
            "tools.search:search_tickets",
            "tools.thinking:thinking",
        ]
        for spec in specs:
            assert callable(resolve_tool(spec))

    def test_field_coordinator_tools_resolve(self):
        """FieldCoordinator tool specs resolve."""
        from agents._tools import resolve_tool
        specs = [
            "tools.graph_explorer:query_graph",
            "tools.search:search_equipment",
            "tools.search:search_infra_specs",
            "tools.thinking:thinking",
        ]
        for spec in specs:
            assert callable(resolve_tool(spec))


class TestScenarioAgentPromptFiles:
    """All prompt files referenced in the real scenario.yaml exist on disk."""

    @pytest.fixture
    def prompts_dir(self):
        """Path to the telecom-playground prompts directory."""
        from app.scenario import get_scenario_dir
        sd = get_scenario_dir()
        if not sd:
            pytest.skip("Scenario directory not available")
        return sd / "data" / "prompts"

    def test_orchestrator_prompts_exist(self, prompts_dir):
        """Orchestrator prompt files exist."""
        files = [
            "orchestrator/orchestrator_preamble.md",
            "orchestrator/investigation_protocol.md",
        ]
        for f in files:
            path = prompts_dir / f
            assert path.exists(), f"Missing prompt: {path}"
            assert path.read_text().strip(), f"Empty prompt: {path}"

    def test_knowledge_analyst_prompts_exist(self, prompts_dir):
        """KnowledgeAnalyst prompt files exist."""
        path = prompts_dir / "knowledge_analyst" / "search_methodology.md"
        assert path.exists(), f"Missing prompt: {path}"

    def test_field_coordinator_prompts_exist(self, prompts_dir):
        """FieldCoordinator prompt files exist."""
        files = [
            "field_coordinator/field_ops_protocol.md",
            "field_coordinator/equipment_context.md",
        ]
        for f in files:
            path = prompts_dir / f
            assert path.exists(), f"Missing prompt: {path}"
