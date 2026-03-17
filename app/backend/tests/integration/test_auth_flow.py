"""Integration tests for auth endpoints — /api/auth_setup, health, etc.

Test layer: integration (FastAPI TestClient, in-process, no real auth).
Verifies that the /api/auth_setup endpoint responds correctly based on
AUTH_ENABLED, and that health/existing endpoints remain unauthenticated.

Follows the project's test convention:
    - asyncio_mode = "auto"
    - Markers: @pytest.mark.integration
    - Uses the existing ``client`` fixture from integration/conftest.py
"""

import os

import pytest

pytestmark = pytest.mark.integration


# ── Tests: /api/auth_setup ──────────────────────────────────────────────────


class TestAuthSetup:
    """Tests for the /api/auth_setup unauthenticated config endpoint."""

    def test_auth_setup_returns_disabled(self, client):
        """AUTH_ENABLED=false → {useLogin: false}."""
        # Default env has AUTH_ENABLED unset (defaults to false)
        res = client.get("/api/auth_setup")
        assert res.status_code == 200
        body = res.json()
        assert body["useLogin"] is False
        # Should NOT include MSAL config keys
        assert "clientId" not in body

    def test_auth_setup_returns_config(self, client, monkeypatch):
        """AUTH_ENABLED=true → includes clientId, authority, scopes."""
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH_CLIENT_ID", "test-app-id-123")
        monkeypatch.setenv("AUTH_TENANT_ID", "common")

        # Must re-create settings to pick up new env vars
        from app.foundation.config import Settings
        import app.main as main_mod
        import app.auth as auth_mod
        import app.routers.auth_setup as auth_setup_mod

        new_settings = Settings()
        monkeypatch.setattr(main_mod, "settings", new_settings)
        monkeypatch.setattr(auth_mod, "settings", new_settings)
        monkeypatch.setattr(auth_setup_mod, "settings", new_settings)

        res = client.get("/api/auth_setup")
        assert res.status_code == 200
        body = res.json()
        assert body["useLogin"] is True
        assert body["clientId"] == "test-app-id-123"
        assert body["authority"] == "https://login.microsoftonline.com/common"
        assert body["scopes"] == ["api://test-app-id-123/access_as_user"]

    def test_auth_setup_always_unauthenticated(self, client):
        """No Authorization header needed for /api/auth_setup — always 200."""
        # No Authorization header in request
        res = client.get("/api/auth_setup")
        assert res.status_code == 200


# ── Tests: health endpoints remain unauthenticated ──────────────────────────


class TestHealthUnauthenticated:
    """Verify health endpoints don't require auth, even when auth is enabled."""

    def test_health_always_unauthenticated(self, client):
        """/health → 200 without any auth token."""
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_existing_routes_unaffected(self, client):
        """Existing session routes still work without auth (AUTH_ENABLED=false)."""
        # Create a session — should still work without auth
        res = client.post("/api/sessions", json={"title": "auth test"})
        assert res.status_code == 201
        session_id = res.json()["id"]

        # List sessions
        res = client.get("/api/sessions")
        assert res.status_code == 200

        # Get session
        res = client.get(f"/api/sessions/{session_id}")
        assert res.status_code == 200

        # Delete session
        res = client.delete(f"/api/sessions/{session_id}")
        assert res.status_code == 204
