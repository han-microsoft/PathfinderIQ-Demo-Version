"""Spoofed tool return shape validation and importability tests.

Tests that each spoofed action tool returns valid JSON with the expected
schema, and that all tool modules are importable via the agents (AgentRegistry)
resolution path.
"""

from __future__ import annotations

import json

import pytest

from tools._spoof_state import reset


@pytest.fixture(autouse=True)
def _clear_spoof_state():
    """Reset spoof state before and after each test."""
    reset()
    yield
    reset()


@pytest.fixture
def _set_session_context():
    """Set a test session_id in the request context."""
    from app.foundation.request_context import RequestContext, set_request_context
    set_request_context(RequestContext(session_id="test_session_001"))
    yield
    # ContextVar auto-cleans per-task; explicit reset not needed in tests


class TestSetLinkStatusTool:
    """set_link_status tool return shape."""

    @pytest.mark.asyncio
    async def test_returns_valid_json(self, _set_session_context):
        """set_link_status returns JSON with status and link fields."""
        from tools.network._set_link_status import set_link_status
        result = await set_link_status(link_id="LINK-1", status="admin_down")
        parsed = json.loads(result)
        assert parsed["status"] == "admin_down"
        assert parsed["link"] == "LINK-1"
        assert "changed_at" in parsed


class TestRerouteTrafficTool:
    """reroute_traffic tool return shape."""

    @pytest.mark.asyncio
    async def test_returns_valid_json(self, _set_session_context):
        """reroute_traffic returns JSON with path and activation time."""
        from tools.network._reroute_traffic import reroute_traffic
        result = await reroute_traffic(backup_path_id="MPLS-BACKUP-02")
        parsed = json.loads(result)
        assert parsed["status"] == "rerouted"
        assert parsed["path"] == "MPLS-BACKUP-02"
        assert "activated_at" in parsed


class TestCreateIncidentTicketTool:
    """create_incident_ticket tool return shape."""

    @pytest.mark.asyncio
    async def test_returns_ticket_id(self, _set_session_context):
        """create_incident_ticket returns JSON with ticket_id starting with INC-."""
        from tools.incidents._create_ticket import create_incident_ticket
        result = await create_incident_ticket(
            severity="SEV-2", title="Test", description="Desc",
            affected_services="SVC-1",
        )
        parsed = json.loads(result)
        assert parsed["ticket_id"].startswith("INC-")
        assert parsed["status"] == "open"
        assert parsed["severity"] == "SEV-2"


class TestUpdateAdvisoryTool:
    """update_advisory tool return shape."""

    @pytest.mark.asyncio
    async def test_returns_advisory_id(self, _set_session_context):
        """update_advisory returns JSON with advisory_id starting with ADV-."""
        from tools.incidents._update_advisory import update_advisory
        result = await update_advisory(
            advisory_text="Test advisory",
            affected_regions="Sydney, Melbourne",
        )
        parsed = json.loads(result)
        assert parsed["advisory_id"].startswith("ADV-")
        assert parsed["status"] == "posted"
        assert parsed["distribution_count"] == 847


class TestToolImportability:
    """All tool modules are importable via the agents (AgentRegistry) resolution path."""

    def test_loader_resolves_network_tools(self):
        """agents._tools.resolve_tool resolves all network tool specs."""
        from agents._tools import resolve_tool
        assert callable(resolve_tool("tools.network:set_link_status"))
        assert callable(resolve_tool("tools.network:reroute_traffic"))

    def test_loader_resolves_incident_tools(self):
        """agents._tools.resolve_tool resolves all incident tool specs."""
        from agents._tools import resolve_tool
        assert callable(resolve_tool("tools.incidents:create_incident_ticket"))
        assert callable(resolve_tool("tools.incidents:update_advisory"))
