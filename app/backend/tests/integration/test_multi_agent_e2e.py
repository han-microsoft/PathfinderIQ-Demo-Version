"""Phase 9 — E2E regression and multi-agent integration tests.

Tests backward compatibility of echo/mock providers, tool importability,
spoof state isolation, and session lifecycle with v2 fields.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with in-memory session store and echo LLM provider."""
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("OTEL_EXPORT_TARGET", "")
    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)
    from app.main import app
    from app.services.session_store.memory import InMemorySessionStore
    from app.services.llm import EchoLLMService
    app.state.store = InMemorySessionStore()
    app.state.llm = EchoLLMService()
    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.startup_status = "ready"
        yield c
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos


class TestEchoProviderNoMultiAgentEvents:
    """Echo provider does not emit multi-agent events."""

    def test_no_agent_switch(self, client):
        """Echo provider SSE stream does not contain agent_switch events."""
        res = client.post("/api/sessions", json={"title": "echo test"})
        sid = res.json()["id"]
        res = client.post(f"/api/chat/{sid}", json={"content": "hello"})
        assert res.status_code == 200
        body = res.text
        assert "agent_switch" not in body
        assert "action_plan_proposal" not in body

    def test_session_has_v3_fields(self, client):
        """Session created via echo provider includes v3 fields."""
        res = client.post("/api/sessions", json={"title": "v3 test"})
        data = res.json()
        assert data["schema_version"] >= 3
        assert "threads" in data

    def test_session_get_has_threads(self, client):
        """GET /api/sessions/{id} response includes threads dict."""
        res = client.post("/api/sessions", json={"title": "v3 test"})
        sid = res.json()["id"]
        res = client.get(f"/api/sessions/{sid}")
        data = res.json()
        assert "threads" in data
        assert isinstance(data["threads"], dict)

    def test_list_sessions_has_summary_fields(self, client):
        """GET /api/sessions summaries include required fields."""
        client.post("/api/sessions", json={"title": "v3 test"})
        res = client.get("/api/sessions")
        summaries = res.json()
        assert len(summaries) > 0
        assert "message_count" in summaries[0]
        assert "tool_call_count" in summaries[0]


class TestThreadEndpoint:
    """Thread lazy-load endpoint tests."""

    def test_unknown_session_returns_404(self, client):
        """GET /sessions/nonexistent/thread/hoff_abc returns 404."""
        res = client.get("/api/sessions/nonexistent/thread/hoff_abc")
        assert res.status_code == 404


class TestAllToolPackagesImportable:
    """Every new tool package from Phases 1-5 is importable."""

    def test_all_packages(self):
        """All tool packages are importable and callable."""
        from tools.network import reroute_traffic, set_link_status
        from tools.incidents import create_incident_ticket, update_advisory
        from tools.search import search_equipment, search_infra_specs
        assert all(callable(t) for t in [
            reroute_traffic, set_link_status,
            create_incident_ticket, update_advisory,
            search_equipment, search_infra_specs,
        ])


class TestSpoofStateSessionIsolation:
    """Verify spoof state doesn't leak across sessions."""

    def test_cross_session_isolation(self):
        """Spoof state for one session does not affect another."""
        from tools._spoof_state import get_link_status, reset, set_link_status
        reset()
        set_link_status("session_a", "LINK-1", "admin_down")
        set_link_status("session_b", "LINK-1", "admin_up")
        assert get_link_status("session_a", "LINK-1")["status"] == "admin_down"
        assert get_link_status("session_b", "LINK-1")["status"] == "admin_up"
        reset()
