"""Agent identity isolation — regression tests for the identity bleed bug.

The saved conversation 32b0bcc2108d4bf4aada0377b52a0534.json showed the
fieldCoordinator agent responding as 'NetworkInvestigator'. These tests
verify that each agent gets its own identity, tools, and prompt — and that
no agent shares state with another.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import MagicMock, patch

from agents import registry
from agents._config import iter_agents, _agents_config_cache


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset agent config cache between tests."""
    original = dict(_agents_config_cache)
    _agents_config_cache.clear()
    yield
    _agents_config_cache.clear()
    _agents_config_cache.update(original)


# Full flat config matching the live telecom-playground scenario
_LIVE_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "NOCOrchestrator",
        "description": "Network operations orchestrator.",
        "instructions": [],
        "tools": [
            "tools.delegation:delegate_to_agent",
            "tools.network:reroute_traffic",
            "tools.thinking:thinking",
        ],
    },
    "networkInvestigator": {
        "name": "NetworkInvestigator",
        "description": "Graph topology expert.",
        "instructions": [],
        "tools": [
            "tools.graph_explorer:query_graph",
            "tools.telemetry:query_telemetry",
            "tools.thinking:thinking",
        ],
    },
    "knowledgeAnalyst": {
        "name": "KnowledgeAnalyst",
        "description": "Runbook and ticket search.",
        "instructions": [],
        "tools": ["tools.search:search_runbooks", "tools.thinking:thinking"],
    },
    "fieldCoordinator": {
        "name": "FieldCoordinator",
        "description": "Field operations specialist.",
        "instructions": [],
        "tools": [
            "tools.graph_explorer:query_graph",
            "tools.search:search_equipment",
            "tools.thinking:thinking",
        ],
    },
}


class TestBuildReturnsCorrectAgent:
    """registry.build(agent_id) returns an agent with that agent's identity."""

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_orchestrator_name(self, mock_dir, mock_yaml, tmp_path):
        """build('orchestrator') → name='NOCOrchestrator'."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path
        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("orchestrator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "NOCOrchestrator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_network_investigator_name(self, mock_dir, mock_yaml, tmp_path):
        """build('networkInvestigator') → name='NetworkInvestigator'."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path
        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("networkInvestigator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "NetworkInvestigator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_field_coordinator_name(self, mock_dir, mock_yaml, tmp_path):
        """build('fieldCoordinator') → name='FieldCoordinator'."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path
        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("fieldCoordinator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        assert call_kwargs.kwargs["name"] == "FieldCoordinator"

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_no_agent_gets_wrong_name(self, mock_dir, mock_yaml, tmp_path):
        """For each agent, the built name matches config — not any other agent's."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path

        for agent_id, agent_cfg in iter_agents(_LIVE_CONFIG):
            mock_client = MagicMock()
            mock_client.as_agent.return_value = MagicMock()
            _agents_config_cache.clear()

            registry.build(agent_id, mock_client)

            call_kwargs = mock_client.as_agent.call_args
            built_name = call_kwargs.kwargs["name"]
            expected_name = agent_cfg["name"]
            assert built_name == expected_name, (
                f"Agent '{agent_id}' built with name '{built_name}', "
                f"expected '{expected_name}'"
            )


class TestBuildReturnsCorrectTools:
    """Each agent receives only the tools listed in its config."""

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_orchestrator_has_delegation_not_query_graph(self, mock_dir, mock_yaml, tmp_path):
        """Orchestrator has reroute_traffic, NOT query_graph."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path
        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("orchestrator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        tools = call_kwargs.kwargs.get("tools") or []
        tool_names = {getattr(t, "name", str(t)) for t in tools}
        assert "reroute_traffic" in tool_names
        assert "query_graph" not in tool_names

    @patch("agents._config.load_scenario_yaml", return_value={"agents": _LIVE_CONFIG})
    @patch("app.scenario.get_scenario_dir")
    def test_investigator_has_query_graph_not_reroute(self, mock_dir, mock_yaml, tmp_path):
        """NetworkInvestigator has query_graph, NOT reroute_traffic."""
        (tmp_path / "data" / "prompts").mkdir(parents=True)
        mock_dir.return_value = tmp_path
        mock_client = MagicMock()
        mock_client.as_agent.return_value = MagicMock()

        registry.build("networkInvestigator", mock_client)

        call_kwargs = mock_client.as_agent.call_args
        tools = call_kwargs.kwargs.get("tools") or []
        tool_names = {getattr(t, "name", str(t)) for t in tools}
        assert "query_graph" in tool_names
        assert "reroute_traffic" not in tool_names


class TestGetPromptReturnsCorrectIdentity:
    """get_prompt() returns the agent's own identity text."""

    def test_field_coordinator_prompt_has_own_name(self):
        """Contains 'FieldCoordinator'."""
        _, name, prompt = registry.get_prompt("fieldCoordinator")
        assert name == "FieldCoordinator"

    def test_field_coordinator_prompt_does_not_contain_other_names(self):
        """Does NOT contain other agents' identity markers."""
        _, _, prompt = registry.get_prompt("fieldCoordinator")
        # The prompt should not contain other agents' IDENTITY headers
        assert "IDENTITY — NOCOrchestrator" not in prompt
        assert "IDENTITY — NetworkInvestigator" not in prompt

    def test_network_investigator_prompt_has_own_name(self):
        """Contains 'NetworkInvestigator'."""
        _, name, prompt = registry.get_prompt("networkInvestigator")
        assert name == "NetworkInvestigator"


class TestThreadSystemPromptIsolation:
    """Per-agent threads in the session store are isolated."""

    def _run(self, coro):
        """Run async code synchronously."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    @patch("agents.registry.get_prompt")
    def test_each_thread_has_correct_system_prompt(self, mock_prompt):
        """Thread for each agent has the correct identity in its system prompt."""
        from app.foundation.models import Session
        from app.services.conversation._session_state import SessionStateManager
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        session = Session(id="test-sess")
        self._run(store.create(session))

        ssm = SessionStateManager()

        # Create threads for two different agents
        mock_prompt.return_value = ("fieldCoordinator", "FieldCoordinator", "You are FieldCoordinator.")
        session = self._run(store.get("test-sess"))
        thread_fc, _ = self._run(ssm.ensure_thread(session, "test-sess", "fieldCoordinator", store))

        mock_prompt.return_value = ("networkInvestigator", "NetworkInvestigator", "You are NetworkInvestigator.")
        session = self._run(store.get("test-sess"))
        thread_ni, _ = self._run(ssm.ensure_thread(session, "test-sess", "networkInvestigator", store))

        # Each thread has the correct system prompt
        assert thread_fc.messages[0].content == "You are FieldCoordinator."
        assert thread_ni.messages[0].content == "You are NetworkInvestigator."

    @patch("agents.registry.get_prompt")
    def test_messages_do_not_cross_threads(self, mock_prompt):
        """Appending to agent A's thread does not affect agent B's thread."""
        from app.foundation.models import Message, Role, Session
        from app.services.conversation._session_state import SessionStateManager
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        session = Session(id="test-sess")
        self._run(store.create(session))

        ssm = SessionStateManager()

        mock_prompt.return_value = ("agentA", "AgentA", "You are A.")
        session = self._run(store.get("test-sess"))
        self._run(ssm.ensure_thread(session, "test-sess", "agentA", store))

        mock_prompt.return_value = ("agentB", "AgentB", "You are B.")
        session = self._run(store.get("test-sess"))
        self._run(ssm.ensure_thread(session, "test-sess", "agentB", store))

        # Append a message to agentA's thread
        msg = Message(role=Role.USER, content="Hello A", agent_name="agentA")
        self._run(store.append_message("test-sess", msg, agent_id="agentA"))

        # Verify agentB's thread is unaffected
        session = self._run(store.get("test-sess"))
        thread_b = session.threads["agentB"]
        non_system = [m for m in thread_b.messages if m.role != Role.SYSTEM]
        assert len(non_system) == 0, "Agent B's thread should have no user messages"

        # Verify agentA got the message
        thread_a = session.threads["agentA"]
        non_system_a = [m for m in thread_a.messages if m.role != Role.SYSTEM]
        assert len(non_system_a) == 1
        assert non_system_a[0].content == "Hello A"
