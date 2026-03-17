"""Tests for per-user scenario isolation via request context."""


class TestScenarioHeaderIsolation:
    """Verify X-Scenario-Name header controls per-request scenario."""

    def test_header_overrides_saved_default(self, client, temp_scenario):
        """Request with X-Scenario-Name header sees that scenario as active."""
        temp_name = temp_scenario("scenario-header-override", graph="fabric")
        resp = client.get(
            "/api/scenarios",
            headers={"X-Scenario-Name": temp_name},
        )
        assert resp.status_code == 200
        assert resp.json()["active"] == temp_name

    def test_different_headers_see_different_active(self, client, temp_scenario):
        """Two requests with different headers see different active scenarios."""
        temp_name = temp_scenario("scenario-header-diff", graph="fabric")
        resp_a = client.get(
            "/api/scenarios",
            headers={"X-Scenario-Name": temp_name},
        )
        resp_b = client.get(
            "/api/scenarios",
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp_a.json()["active"] == temp_name
        assert resp_b.json()["active"] == "telecom-playground-v2"


class TestScenarioSwitchDoesNotAffectOtherRequests:
    """Verify that POST /api/scenarios/select does not bleed to other users."""

    def test_switch_does_not_affect_request_with_header(self, client, temp_scenario):
        """One user's scenario switch does not affect a request with its own header."""
        temp_name = temp_scenario("scenario-user-isolation", graph="fabric", topology_node_count=2)
        # User A switches
        client.post(
            "/api/scenarios/select",
            json={"scenario": temp_name},
        )

        # User B checks with their own header — NOT affected by User A
        resp_b = client.get(
            "/api/scenarios",
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp_b.json()["active"] == "telecom-playground-v2"


class TestTopologyAndScenarioInfoIsolation:
    """Verify /api/scenario and /api/scenario/topology use per-request context."""

    def test_topology_returns_correct_scenario_data(self, client, temp_scenario):
        """GET /api/scenario/topology with X-Scenario-Name returns that scenario's topology."""
        temp_name = temp_scenario("scenario-topology-small", graph="fabric", topology_node_count=2)
        resp_hw = client.get(
            "/api/scenario/topology",
            headers={"X-Scenario-Name": temp_name},
        )
        assert resp_hw.status_code == 200
        hw_nodes = resp_hw.json().get("topology_nodes", resp_hw.json().get("nodes", []))

        resp_tp = client.get(
            "/api/scenario/topology",
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp_tp.status_code == 200
        tp_nodes = resp_tp.json().get("topology_nodes", resp_tp.json().get("nodes", []))

        # They must have different node counts
        assert len(hw_nodes) != len(tp_nodes), (
            f"Both scenarios returned {len(hw_nodes)} nodes — topology not isolated"
        )
        assert len(hw_nodes) < 10, f"temporary scenario should have few nodes, got {len(hw_nodes)}"
        assert len(tp_nodes) > 50, f"telecom should have many nodes, got {len(tp_nodes)}"

    def test_scenario_info_returns_correct_metadata(self, client, temp_scenario):
        """GET /api/scenario with X-Scenario-Name returns that scenario's metadata."""
        temp_name = temp_scenario("scenario-info-small", graph="fabric")
        resp_hw = client.get(
            "/api/scenario",
            headers={"X-Scenario-Name": temp_name},
        )
        assert resp_hw.status_code == 200
        assert resp_hw.json()["scenario_name"] == temp_name

        resp_tp = client.get(
            "/api/scenario",
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp_tp.status_code == 200
        assert resp_tp.json()["scenario_name"] == "telecom-playground-v2"

    def test_topology_not_affected_by_global_switch(self, client, temp_scenario):
        """User A switches scenarios, User B still gets telecom topology."""
        temp_name = temp_scenario("scenario-topology-isolated", graph="fabric", topology_node_count=2)
        client.post("/api/scenarios/select", json={"scenario": temp_name})

        resp = client.get(
            "/api/scenario/topology",
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp.status_code == 200
        nodes = resp.json().get("topology_nodes", resp.json().get("nodes", []))
        assert len(nodes) > 50, "Should get telecom topology despite global switch"


class TestSessionCreationIsolation:
    """Verify session creation uses per-request scenario, not global state."""

    def test_session_created_with_header_scenario(self, client, temp_scenario):
        """Session should record the scenario from the X-Scenario-Name header,
        not the global os.environ SCENARIO_NAME."""
        temp_name = temp_scenario("scenario-session-header", graph="fabric")
        client.post("/api/scenarios/select", json={"scenario": temp_name})

        # Create session with telecom header
        resp = client.post(
            "/api/sessions",
            json={},
            headers={"X-Scenario-Name": "telecom-playground-v2"},
        )
        assert resp.status_code == 201
        session = resp.json()
        assert session["scenario_name"] == "telecom-playground-v2", (
            f"Session recorded '{session['scenario_name']}' instead of 'telecom-playground-v2'. "
            "Session creation is reading from global state, not per-request context."
        )


class TestScenarioHealthIsolation:
    """Verify /api/scenario/health uses per-request context."""

    def test_scenario_health_uses_header(self, client, temp_scenario):
        """Scenario health check should report the header's scenario name."""
        temp_name = temp_scenario("scenario-health-header", graph="fabric")
        resp = client.get(
            "/api/scenario/health",
            headers={"X-Scenario-Name": temp_name},
        )
        assert resp.status_code == 200
        checks = resp.json().get("checks", {})
        assert checks.get("scenario_name") == temp_name
