"""Page refresh isolation tests for scenario-only bootstrap."""


class TestPageRefreshIsolation:
    """The core bug: refresh should NOT inherit another user's state."""

    def test_refresh_after_other_user_switch(self, client_as, temp_scenario):
        """User B must not inherit User A's saved scenario on refresh."""
        user_a = client_as("user-a")
        user_b = client_as("user-b")
        temp_name = temp_scenario("refresh-user-a", graph="fabric")

        # User A switches
        resp = user_a.post(
            "/api/scenarios/select",
            json={"scenario": temp_name},
        )
        assert resp.status_code == 200

        # User B reads preferences — should get defaults, not user A's state
        resp_b = user_b.get("/api/preferences")
        assert resp_b.status_code == 200
        prefs_b = resp_b.json()
        # User B never switched — should get defaults
        assert prefs_b["scenario_name"] != temp_name, (
            f"User B inherited User A's scenario: {prefs_b['scenario_name']}"
        )

    def test_refresh_preserves_own_switch(self, client_as, temp_scenario):
        """A user's own scenario choice persists across refresh."""
        user_b = client_as("user-b-persist")
        temp_name = temp_scenario("refresh-user-b", graph="fabric")

        # User B switches
        user_b.post(
            "/api/scenarios/select",
            json={"scenario": temp_name},
        )

        # User B reads preferences — should persist
        resp = user_b.get("/api/preferences")
        assert resp.json()["scenario_name"] == temp_name

    def test_two_users_different_scenarios(self, client_as, temp_scenario):
        """Two users switch to different scenarios. Each sees their own."""
        user_a = client_as("user-a-diff")
        user_b = client_as("user-b-diff")
        temp_name = temp_scenario("refresh-user-a-diff", graph="fabric")

        user_a.post("/api/scenarios/select", json={"scenario": temp_name})
        user_b.post("/api/scenarios/select", json={"scenario": "telecom-playground-v2"})

        # Each sees their own
        prefs_a = user_a.get("/api/preferences").json()
        prefs_b = user_b.get("/api/preferences").json()
        assert prefs_a["scenario_name"] == temp_name
        assert prefs_b["scenario_name"] == "telecom-playground-v2"


class TestPreferencesAPI:
    """Tests for GET /api/preferences endpoint behavior."""

    def test_returns_defaults_for_new_user(self, client_as):
        """A user who never switched gets defaults from seed.yaml/env."""
        user = client_as("brand-new-user")
        resp = user.get("/api/preferences")
        assert resp.status_code == 200
        data = resp.json()
        # Preferences are now scenario-only.
        assert "scenario_name" in data
        assert set(data.keys()) == {"scenario_name"}

class TestEnvVarImmutability:
    """Verify that switch endpoints do NOT mutate os.environ."""

    def test_scenario_switch_no_env_mutation(self, client_as, temp_scenario):
        """os.environ['SCENARIO_NAME'] is not changed by scenario switch."""
        import os
        original = os.environ.get("SCENARIO_NAME")  # May be None or a string
        user = client_as("env-test-user")
        temp_name = temp_scenario("refresh-env-user", graph="fabric")
        user.post("/api/scenarios/select", json={"scenario": temp_name})
        assert os.environ.get("SCENARIO_NAME") == original
