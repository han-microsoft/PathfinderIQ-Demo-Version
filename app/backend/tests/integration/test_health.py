"""Health check integration tests."""


def test_shallow_health(client):
    """GET /health returns 200 with status ok and startup_status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "provider" in data
    assert "startup_status" in data


def test_deep_health_ready(client):
    """GET /health/ready returns component-level statuses."""
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "checks" in data
    # Session store should be ok (in-memory, always available)
    assert data["checks"]["session_store"]["status"] == "ok"


def test_scenario_endpoint(client):
    """GET /api/scenario returns scenario metadata."""
    res = client.get("/api/scenario")
    assert res.status_code == 200
    data = res.json()
    assert "scenario_name" in data
    assert "display_name" in data


def test_scenario_endpoint_exposes_replay_tour(client):
    """GET /api/scenario exposes scenario-owned replay tour metadata when configured."""
    res = client.get(
        "/api/scenario",
        headers={"X-Scenario-Name": "telecom-playground-v2"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["scenario_name"] == "telecom-playground-v2"
    assert data["replay_tour"]
    assert data["replay_tour"][0]["title"] == "Scenario Overview"
    assert data["replay_tour_detailed"]
    assert data["replay_tour_detailed"][0]["title"] == "Scenario Overview"
    assert data["replay_highlights"]
    assert data["replay_conversation_url"].startswith("/api/scenario/assets/ui/")
    assert "scenario=telecom-playground-v2" in data["replay_conversation_url"]
    assert data["replay_tour"][1]["agentImage"].startswith("/api/scenario/assets/")
    assert "scenario=telecom-playground-v2" in data["replay_tour"][1]["agentImage"]


def test_scenario_asset_endpoint_serves_scenario_local_files(client):
    """GET /api/scenario/assets serves files from the active scenario root only."""
    res = client.get(
        "/api/scenario/assets/ui/assets/agents/nocorchestrator_headshot.png?scenario=telecom-playground-v2",
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content


def test_scenario_asset_endpoint_uses_explicit_scenario_query(client):
    """GET /api/scenario/assets honors an explicit scenario query for public asset fetches."""
    res = client.get(
        "/api/scenario/assets/ui/replay_conversation.json?scenario=telecom-playground-v2",
    )
    assert res.status_code == 200


def test_scenario_asset_endpoint_rejects_non_ui_paths(client):
    """GET /api/scenario/assets does not expose non-UI scenario files."""
    res = client.get(
        "/api/scenario/assets/data/prompts/core_rules.md?scenario=telecom-playground-v2",
    )
    assert res.status_code == 404


def test_topology_endpoint(client):
    """GET /api/scenario/topology returns topology data."""
    res = client.get("/api/scenario/topology")
    assert res.status_code == 200
    data = res.json()
    # Should have one of these keys
    assert "topology_nodes" in data or "nodes" in data
