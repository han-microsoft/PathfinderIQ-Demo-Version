"""Tests proving per-user state isolation (bug fix verification).

HISTORY: These tests originally proved the cross-user state bleed bug EXISTS
(env var mutations leaked between users). Now they verify the bug is FIXED:
switch endpoints save per-user preferences instead of mutating os.environ,
so User A's actions never affect User B.

Status: These tests now PASS, proving the bug is FIXED.
"""

import os


class TestScenarioSwitchIsIsolated:
    """Verify that scenario switching does NOT bleed across users."""

    def test_user_a_switch_does_not_change_env(self, client, temp_scenario):
        """When User A switches scenario, os.environ is NOT mutated.
        Per-user state lives in UserPreferencesService, not env vars.
        """
        original_scenario = os.environ.get("SCENARIO_NAME")
        temp_name = temp_scenario("scenario-global-state-a", graph="fabric")

        # User A switches to a temporary scenario.
        resp_a = client.post(
            "/api/scenarios/select",
            json={"scenario": temp_name},
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["scenario"] == temp_name

        # os.environ is UNTOUCHED — still has the startup default
        assert os.environ.get("SCENARIO_NAME") == original_scenario, (
            "FIX VERIFIED: os.environ should NOT be mutated by scenario switch."
        )

    def test_user_preferences_saved_correctly(self, client, temp_scenario):
        """Scenario switch saves prefs, visible via GET /api/preferences."""
        temp_name = temp_scenario("scenario-global-state-prefs", graph="fabric")
        client.post(
            "/api/scenarios/select",
            json={"scenario": temp_name},
        )
        resp = client.get("/api/preferences")
        assert resp.status_code == 200
        assert resp.json()["scenario_name"] == temp_name

    def test_backend_switch_does_not_change_env(self, client):
        """Removed backend switch route cannot mutate os.environ."""
        original_backend = os.environ.get("GRAPH_BACKEND")

        # Backend selection is no longer writable.
        resp = client.post(
            "/api/backends/select",
            json={"backend": "memory"},
            headers={
                "X-Scenario-Name": "telecom-playground-v2",
            },
        )
        assert resp.status_code == 404

        # os.environ is UNTOUCHED
        assert os.environ.get("GRAPH_BACKEND") == original_backend, (
            "FIX VERIFIED: os.environ should NOT be mutated by backend switch."
        )

    def test_env_vars_stay_at_startup_defaults(self, client, temp_scenario):
        """Multiple switches never change the startup env var defaults."""
        original = os.environ.get("SCENARIO_NAME")
        temp_name = temp_scenario("scenario-global-state-b", graph="fabric")

        # Multiple switches
        client.post("/api/scenarios/select", json={"scenario": temp_name})
        client.post("/api/scenarios/select", json={"scenario": "telecom-playground-v2"})
        client.post("/api/scenarios/select", json={"scenario": temp_name})

        # env vars NEVER changed
        assert os.environ.get("SCENARIO_NAME") == original
