"""Integration tests for scenario asset access.

This test lives outside the broad endpoint auth sweep because the asset route
has intentionally different behavior from the rest of the scenario endpoints:
browser image tags and replay payload fetches must be able to load UI files
without an Authorization header.
"""

from __future__ import annotations


def test_scenario_assets_allow_unauthenticated_ui_files(auth_enabled_client):
    """GET /api/scenario/assets allows unauthenticated reads for UI assets."""
    res = auth_enabled_client.get(
        "/api/scenario/assets/ui/assets/agents/nocorchestrator_headshot.png?scenario=telecom-playground-v2",
    )
    assert res.status_code == 200