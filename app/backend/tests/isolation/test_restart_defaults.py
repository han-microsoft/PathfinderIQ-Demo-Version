"""Restart defaults regression tests for scenario-only preferences."""

import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestRestartDefaults:
    """Verify restart defaults come from env vars, not from user actions."""

    def test_restart_ignores_previous_user_switches(self, client_as, temp_scenario):
        """After user switches + simulated restart, defaults = env vars.

        The InMemoryPreferencesStore is recreated on restart with fresh
        defaults from env vars, so previous user preferences are lost.
        """
        user_a = client_as("restart-user-a")
        temp_name = temp_scenario("restart-user-a-scenario", graph="fabric")

        # User A switches scenario.
        user_a.post("/api/scenarios/select", json={"scenario": temp_name})

        # Verify user A's prefs are saved
        prefs_a = user_a.get("/api/preferences").json()
        assert prefs_a["scenario_name"] == temp_name

        # Simulate restart: clear the preferences store
        from app.main import app
        from app.services.preferences import InMemoryPreferencesStore, UserPreferences

        # Re-create the store with env var defaults (simulates restart)
        app.state.preferences = InMemoryPreferencesStore(
            UserPreferences(
                scenario_name=os.environ.get("SCENARIO_NAME", ""),
            )
        )

        # After "restart", user B should see env var defaults
        user_b = client_as("restart-user-b")
        prefs_b = user_b.get("/api/preferences").json()
        # User B's scenario should be the env var default, not User A's scenario.
        assert prefs_b["scenario_name"] != temp_name, (
            "Restart should reset prefs to env var defaults, not last user's state"
        )

    def test_control_env_not_modified_by_switch(self, client_as):
        """Switch endpoints must NOT write per-user state to control/.env."""
        from pathlib import Path

        control_env = Path(__file__).resolve().parents[2] / "control" / ".env"
        if not control_env.exists():
            # In test environments, control/.env may not exist — skip
            import pytest
            pytest.skip("control/.env not found")

        before = control_env.read_text()

        user = client_as("env-file-user")
        user.post("/api/scenarios/select", json={"scenario": "telecom-playground-v2"})

        after = control_env.read_text()
        assert before == after, "control/.env should NOT be modified by switch endpoints"
