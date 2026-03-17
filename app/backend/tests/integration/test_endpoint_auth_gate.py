"""Integration tests — verify all non-SSE endpoints require auth when AUTH_ENABLED=true.

Test layer: integration (FastAPI TestClient, no real auth).
Each test calls an endpoint WITHOUT an auth token and expects 401.
Companion tests verify AUTH_ENABLED=false still allows access (dev mode bypass).

Follows the project's test convention:
    - asyncio_mode = "auto"
    - Markers: @pytest.mark.integration
    - Uses ``auth_enabled_client`` and ``client`` fixtures from conftest.py
"""

import pytest

pytestmark = pytest.mark.integration

# Every endpoint that MUST require auth when AUTH_ENABLED=true.
# SSE EventSource endpoints are tested separately in Phase 3.
PROTECTED_ENDPOINTS = [
    ("GET", "/api/observability/status"),
    ("GET", "/api/config"),
    ("GET", "/api/config/status"),
    ("GET", "/api/agents/"),
    ("GET", "/api/backends"),
    ("GET", "/api/models/"),
    ("GET", "/api/services/health"),
    ("GET", "/api/scenario"),
    ("GET", "/api/scenario/topology"),
    ("GET", "/api/scenario/health"),
    ("GET", "/api/scenario/agent-prompt"),
    ("GET", "/api/scenarios"),
]

# Endpoints that MUST remain unauthenticated always.
PUBLIC_ENDPOINTS = [
    ("GET", "/health"),
    ("GET", "/health/ready"),
    ("GET", "/api/auth_setup"),
    # POST observability endpoints stay open — console interceptor
    # sends fire-and-forget logs without auth headers.
    ("POST", "/api/observability/logs/frontend"),
    ("POST", "/api/observability/logs/frontend/batch"),
]


class TestProtectedEndpointsReject401:
    """All protected endpoints → 401 without token when auth enabled."""

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_rejects_without_token(self, method, path, auth_enabled_client):
        """Endpoint returns 401 when no Authorization header is sent."""
        client = auth_enabled_client
        res = getattr(client, method.lower())(path)
        assert res.status_code == 401, f"{method} {path} → {res.status_code}, expected 401"


class TestPublicEndpointsAlwaysOpen:
    """Public endpoints → 200/204 regardless of auth mode."""

    def test_health_without_token(self, client):
        """Health probe works without auth token."""
        assert client.get("/health").status_code == 200

    def test_health_ready_without_token(self, client):
        """Readiness probe works without auth token."""
        assert client.get("/health/ready").status_code == 200

    def test_auth_setup_without_token(self, client):
        """MSAL bootstrap endpoint works without auth token."""
        assert client.get("/api/auth_setup").status_code == 200

    def test_observability_frontend_post_without_token(self, client):
        """POST /observability/logs/frontend stays open (console interceptor)."""
        res = client.post(
            "/api/observability/logs/frontend",
            json={"ts": "00:00:00.000", "level": "INFO", "name": "test", "msg": "test"},
        )
        assert res.status_code in (200, 204)

    def test_observability_frontend_batch_without_token(self, client):
        """POST /observability/logs/frontend/batch stays open."""
        res = client.post(
            "/api/observability/logs/frontend/batch",
            json=[{"ts": "00:00:00.000", "level": "INFO", "name": "test", "msg": "test"}],
        )
        assert res.status_code in (200, 204)


class TestDevModeBypass:
    """AUTH_ENABLED=false → all endpoints accessible without token."""

    @pytest.mark.parametrize("method,path", PROTECTED_ENDPOINTS)
    def test_dev_mode_allows_all(self, method, path, client):
        """When auth disabled, protected endpoints still work (no 401)."""
        res = getattr(client, method.lower())(path)
        assert res.status_code != 401, f"{method} {path} returned 401 in dev mode"
