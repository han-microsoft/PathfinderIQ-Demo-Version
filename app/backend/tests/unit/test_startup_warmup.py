"""Tests for two-phase startup and background warm-up.

Verifies that:
1. ``_background_warmup()`` sets startup_status="ready" on completion.
2. ``/health`` includes startup_status field.
3. ``/health/ready`` returns 503 during warm-up (gated on startup_status).

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python -m pytest tests/unit/test_startup_warmup.py -v
"""

import asyncio
import os

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def env_setup():
    """Set test env vars for all tests in this module."""
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("OTEL_EXPORT_TARGET", "")
    yield


class TestBackgroundWarmup:
    """Tests for _background_warmup function."""

    @pytest.mark.asyncio
    async def test_warmup_sets_ready_status(self):
        """After warmup completes, startup_status is 'ready'."""
        from app.main import _background_warmup

        mock_app = MagicMock()
        mock_app.state = MagicMock()
        mock_app.state.startup_status = "warming"
        mock_app.state.store = MagicMock()

        with patch("app.main.settings") as mock_settings:
            mock_settings.cosmos_session_endpoint = ""
            mock_settings.scenario_name = ""
            await _background_warmup(mock_app, None)

        assert mock_app.state.startup_status == "ready"


class TestHealthEndpoints:
    """Test /health and /health/ready reflect startup_status."""

    def test_health_includes_startup_status(self):
        """GET /health includes startup_status field."""
        from fastapi.testclient import TestClient

        saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            # Background warmup may or may not have completed — override
            # for deterministic test
            app.state.startup_status = "ready"
            res = client.get("/health")
            assert res.status_code == 200
            data = res.json()
            assert data["startup_status"] == "ready"

        if saved_cosmos is not None:
            os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos

    def test_health_ready_returns_503_during_warming(self):
        """GET /health/ready returns 503 when startup_status is warming."""
        from fastapi.testclient import TestClient

        saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            # Force warming state
            app.state.startup_status = "warming"
            res = client.get("/health/ready")
            assert res.status_code == 503
            data = res.json()
            assert data["status"] == "warming"

        if saved_cosmos is not None:
            os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos
