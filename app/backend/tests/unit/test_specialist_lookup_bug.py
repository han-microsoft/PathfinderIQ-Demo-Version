"""
Test for flat agent config lookup — all agents are top-level peers.

Historical context:
    The old nested specialists: format caused a bug where config.get()
    couldn't find agents nested under specialists:. That format is now
    removed. All agents are flat peers under agents:.

This test:
    1. Verifies find_agent finds all agents by ID
    2. Verifies find_agent returns None for nonexistent agents
    3. Verifies iter_agents lists all agents, skips reserved keys
"""

import pytest
from unittest.mock import patch

from agents._config import find_agent, iter_agents


# ── Flat multi-agent config ─────────────────────────────────────────────

FLAT_AGENT_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "NOCOrchestrator",
        "description": "Routes tasks",
        "instructions": ["orch_preamble.md"],
        "tools": ["tools.thinking:thinking"],
    },
    "networkInvestigator": {
        "name": "NetworkInvestigator",
        "description": "Graph queries",
        "instructions": ["net_inv_identity.md"],
        "tools": ["tools.graph_explorer:query_graph", "tools.thinking:thinking"],
    },
    "fieldCoordinator": {
        "name": "FieldCoordinator",
        "description": "Field ops",
        "instructions": ["field_coord_identity.md"],
        "tools": ["tools.graph_explorer:query_graph", "tools.search:search_equipment"],
    },
}


class TestFlatAgentLookup:
    """All agents are findable by ID in the flat config."""

    def test_find_orchestrator(self):
        """Orchestrator found by ID."""
        result = find_agent(FLAT_AGENT_CONFIG, "orchestrator")
        assert result is not None
        assert result["name"] == "NOCOrchestrator"

    def test_find_network_investigator(self):
        """NetworkInvestigator found by ID."""
        result = find_agent(FLAT_AGENT_CONFIG, "networkInvestigator")
        assert result is not None
        assert result["name"] == "NetworkInvestigator"

    def test_find_field_coordinator(self):
        """FieldCoordinator found by ID."""
        result = find_agent(FLAT_AGENT_CONFIG, "fieldCoordinator")
        assert result is not None
        assert result["name"] == "FieldCoordinator"

    def test_find_nonexistent_returns_none(self):
        """Missing agent returns None."""
        result = find_agent(FLAT_AGENT_CONFIG, "nonExistentAgent")
        assert result is None

    def test_iter_agents_lists_all(self):
        """iter_agents returns all agents, skips reserved keys."""
        available = [aid for aid, _ in iter_agents(FLAT_AGENT_CONFIG)]
        assert "orchestrator" in available
        assert "networkInvestigator" in available
        assert "fieldCoordinator" in available
        assert "default" not in available
        assert len(available) == 3
