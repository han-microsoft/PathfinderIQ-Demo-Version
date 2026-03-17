"""
Agent configuration correctness tests — verifies each agent gets the right
prompt files, tools, and identity from scenario.yaml.

Tests:
  1. list_agent_definitions returns all agents with correct metadata
  2. Each agent has its own name, description, tool list (no sharing)
  3. Default agent is correctly identified
  4. Tool counts match the scenario.yaml specification
  5. Specialist IDs are distinct from each other and from orchestrator
"""

import os
import pytest
import yaml
import tempfile
from unittest.mock import patch
from pathlib import Path

from agents import registry; from agents._config import iter_agents


# ── Fixture: multi-agent flat config ─────────────────────────────────────────

MULTI_AGENT_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "TestOrchestrator",
        "description": "Routes tasks to specialists",
        "instructions": ["orch_preamble.md"],
        "tools": [
            "tools.thinking:thinking",
            "tools.dispatch:dispatch_field_engineer",
        ],
    },
    "specialist_a": {
        "name": "AlphaSpecialist",
        "description": "Handles graph queries",
        "instructions": ["alpha_identity.md"],
        "tools": [
            "tools.graph_explorer:query_graph",
            "tools.thinking:thinking",
        ],
    },
    "specialist_b": {
        "name": "BetaSpecialist",
        "description": "Handles search queries",
        "instructions": ["beta_identity.md"],
        "tools": [
            "tools.search:search_runbooks",
            "tools.search:search_tickets",
            "tools.thinking:thinking",
        ],
    },
}

class TestIterAgentEntries:
    """_iter_agent_entries correctly flattens all agent definitions."""

    def test_multi_agent_includes_orchestrator_and_specialists(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        ids = [eid for eid, _ in entries]

        assert "orchestrator" in ids
        assert "specialist_a" in ids
        assert "specialist_b" in ids

    def test_multi_agent_excludes_reserved_keys(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        ids = [eid for eid, _ in entries]
        assert "default" not in ids
        assert "specialists" not in ids

    def test_each_entry_has_name_and_tools(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        for agent_id, cfg in entries:
            assert "name" in cfg, f"Agent {agent_id} missing 'name'"
            assert "tools" in cfg, f"Agent {agent_id} missing 'tools'"


class TestAgentConfigIsolation:
    """Each agent's config is independent — no tool/instruction sharing."""

    def test_orchestrator_tools_differ_from_specialists(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        configs = {eid: cfg for eid, cfg in entries}

        orch_tools = set(configs["orchestrator"]["tools"])
        alpha_tools = set(configs["specialist_a"]["tools"])
        beta_tools = set(configs["specialist_b"]["tools"])

        # Orchestrator has dispatch but specialists don't
        assert "tools.dispatch:dispatch_field_engineer" in orch_tools
        assert "tools.dispatch:dispatch_field_engineer" not in alpha_tools
        assert "tools.dispatch:dispatch_field_engineer" not in beta_tools

        # Alpha has query_graph but orchestrator doesn't
        assert "tools.graph_explorer:query_graph" in alpha_tools
        assert "tools.graph_explorer:query_graph" not in orch_tools

        # Beta has search tools but others don't
        assert "tools.search:search_runbooks" in beta_tools
        assert "tools.search:search_runbooks" not in orch_tools
        assert "tools.search:search_runbooks" not in alpha_tools

    def test_each_specialist_has_unique_name(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        names = [cfg["name"] for _, cfg in entries]

        assert len(names) == len(set(names)), (
            f"Duplicate agent names found: {names}"
        )

    def test_each_specialist_has_unique_instructions(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        instruction_sets = [
            tuple(cfg.get("instructions", []))
            for _, cfg in entries
        ]

        # Each agent should have distinct instructions
        assert len(instruction_sets) == len(set(instruction_sets)), (
            "Multiple agents share identical instruction files"
        )

    def test_each_specialist_has_own_description(self):
        entries = iter_agents(MULTI_AGENT_CONFIG)
        descriptions = [cfg.get("description", "").strip() for _, cfg in entries]

        assert len(descriptions) == len(set(descriptions)), (
            "Multiple agents share identical descriptions"
        )


class TestListAgentDefinitions:
    """list_agent_definitions returns correct metadata for the frontend."""

    def _mock_and_call(self, config: dict) -> list[dict]:
        """Patch load_agents_block to return our test config."""
        with patch("agents.load_agents_block", return_value=config):
            return registry.list_definitions()

    def test_multi_agent_returns_all_agents(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)
        ids = [a["id"] for a in result]

        assert "orchestrator" in ids
        assert "specialist_a" in ids
        assert "specialist_b" in ids
        assert len(result) == 3

    def test_each_agent_has_required_fields(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)

        for agent in result:
            assert "id" in agent
            assert "name" in agent
            assert "description" in agent
            assert "tool_count" in agent
            assert "is_default" in agent

    def test_default_agent_is_correctly_marked(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)

        defaults = [a for a in result if a["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "orchestrator"

    def test_non_default_agents_are_not_marked_default(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)

        non_defaults = [a for a in result if not a["is_default"]]
        assert len(non_defaults) == 2
        non_default_ids = {a["id"] for a in non_defaults}
        assert non_default_ids == {"specialist_a", "specialist_b"}

    def test_tool_counts_match_config(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)
        by_id = {a["id"]: a for a in result}

        assert by_id["orchestrator"]["tool_count"] == 2  # thinking + dispatch
        assert by_id["specialist_a"]["tool_count"] == 2  # query_graph + thinking
        assert by_id["specialist_b"]["tool_count"] == 3  # search_runbooks + search_tickets + thinking

    def test_agent_names_match_config(self):
        result = self._mock_and_call(MULTI_AGENT_CONFIG)
        by_id = {a["id"]: a for a in result}

        assert by_id["orchestrator"]["name"] == "TestOrchestrator"
        assert by_id["specialist_a"]["name"] == "AlphaSpecialist"
        assert by_id["specialist_b"]["name"] == "BetaSpecialist"
