"""Tests for the GET /api/agents endpoint.

Validates that the agents router returns agent metadata from scenario.yaml,
including the default agent flag.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """Reset agent config cache between tests."""
    import agents._config as config_mod
    original_cache = dict(config_mod._agents_config_cache)
    config_mod._agents_config_cache.clear()
    yield
    config_mod._agents_config_cache.clear()
    config_mod._agents_config_cache.update(original_cache)


# Flat agent config for mocking — matches the new scenario.yaml format
_MOCK_AGENTS_CONFIG = {
    "default": "orchestrator",
    "orchestrator": {
        "name": "NOCOrchestrator",
        "description": "Network operations orchestrator.",
        "instructions": [],
        "tools": ["tools.thinking:thinking", "tools.network:reroute_traffic"],
        "ui": {
            "headshot": "ui/assets/agents/nocorchestrator_headshot.png",
            "full_body": "ui/assets/agents/nocorchestrator_fullbody.png",
            "product_summary": "Scenario-defined orchestrator summary.",
            "powered_by": [
                {
                    "logo": "ui/assets/logos/foundryiq-logo.png",
                    "label": "Azure AI Foundry",
                    "description": "Scenario-defined product metadata.",
                }
            ],
        },
    },
    "network_investigator": {
        "name": "NetworkInvestigator",
        "description": "Graph topology expert.",
        "instructions": [],
        "tools": ["tools.thinking:thinking"],
    },
}


class TestAgentsEndpoint:
    """GET /api/agents returns agent metadata."""

    @pytest.mark.asyncio
    @patch("agents.load_agents_block", return_value=_MOCK_AGENTS_CONFIG)
    async def test_returns_all_agents(self, mock_yaml):
        """Response contains all defined agents."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/agents/")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            ids = [d["id"] for d in data]
            assert "orchestrator" in ids
            assert "network_investigator" in ids
            assert len(data) == 2

    @pytest.mark.asyncio
    @patch("agents.load_agents_block", return_value=_MOCK_AGENTS_CONFIG)
    async def test_default_flag_set(self, mock_yaml):
        """Only the default agent has is_default=True."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/agents/")
            data = resp.json()
            defaults = [d for d in data if d["is_default"]]
            assert len(defaults) == 1
            assert defaults[0]["id"] == "orchestrator"

    @pytest.mark.asyncio
    @patch("agents.load_agents_block", return_value=_MOCK_AGENTS_CONFIG)
    async def test_response_shape(self, mock_yaml):
        """Each entry has the expected fields."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/agents/")
            for agent in resp.json():
                assert "id" in agent
                assert "name" in agent
                assert "description" in agent
                assert "tool_count" in agent
                assert "is_default" in agent

    @pytest.mark.asyncio
    @patch("agents.load_agents_block", return_value=_MOCK_AGENTS_CONFIG)
    async def test_tool_count_matches(self, mock_yaml):
        """tool_count reflects the number of tools in config."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/agents/")
            data = resp.json()
            orch = next(d for d in data if d["id"] == "orchestrator")
            assert orch["tool_count"] == 2

    @pytest.mark.asyncio
    @patch("agents.build_scenario_asset_url", side_effect=lambda path: f"/api/scenario/assets/{path}?scenario=telecom-playground-v2" if path else None)
    @patch("agents.load_agents_block", return_value=_MOCK_AGENTS_CONFIG)
    async def test_returns_scenario_ui_metadata(self, mock_yaml, mock_asset_url):
        """Agent UI metadata is projected from scenario.yaml into the API payload."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/agents/")
            assert resp.status_code == 200
            orchestrator = next(agent for agent in resp.json() if agent["id"] == "orchestrator")
            assert orchestrator["headshot_url"] == "/api/scenario/assets/ui/assets/agents/nocorchestrator_headshot.png?scenario=telecom-playground-v2"
            assert orchestrator["full_body_url"] == "/api/scenario/assets/ui/assets/agents/nocorchestrator_fullbody.png?scenario=telecom-playground-v2"
            assert orchestrator["product_summary"] == "Scenario-defined orchestrator summary."
            assert orchestrator["powered_by"] == [
                {
                    "logo_url": "/api/scenario/assets/ui/assets/logos/foundryiq-logo.png?scenario=telecom-playground-v2",
                    "label": "Azure AI Foundry",
                    "description": "Scenario-defined product metadata.",
                }
            ]
