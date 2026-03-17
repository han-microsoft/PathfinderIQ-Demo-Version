"""Isolation test fixtures — multi-user test client factory.

Provides ``client_as`` fixture: a factory that  returns test clients
authenticated as specific users via FastAPI dependency_overrides.
Each user gets a distinct OID so preferences are isolated.

Also provides the standard ``client`` fixture from the integration layer
for tests that don't need multi-user simulation.
"""

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Single-user test client (same as integration conftest)."""
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


@pytest.fixture
def client_as(client):
    """Factory: returns a test client that authenticates as a specific user.

    Usage:
        def test_something(client_as):
            client_a = client_as("user-a-oid")
            client_b = client_as("user-b-oid")
            # client_a and client_b share the same TestClient but have
            # different user identities for auth-dependent endpoints.

    The factory overrides ``get_current_user`` dependency to return a User
    with the given OID. Each call returns the SAME underlying TestClient
    (the app is shared), but with a different user identity.
    """
    from app.auth import User, get_current_user
    from app.main import app

    # Track the current "active" user OID via closure
    _active_oid = {"value": "anonymous"}

    async def _make_user_override(request=None):
        """Return a User with the currently active OID."""
        oid = _active_oid["value"]
        return User(oid=oid, email=f"{oid}@test.com", name=f"Test-{oid}")

    app.dependency_overrides[get_current_user] = _make_user_override

    class _UserClient:
        """Thin wrapper that sets the active OID before each request."""
        def __init__(self, oid: str):
            self._oid = oid

        def get(self, *args, **kwargs):
            _active_oid["value"] = self._oid
            return client.get(*args, **kwargs)

        def post(self, *args, **kwargs):
            _active_oid["value"] = self._oid
            return client.post(*args, **kwargs)

        def put(self, *args, **kwargs):
            _active_oid["value"] = self._oid
            return client.put(*args, **kwargs)

        def delete(self, *args, **kwargs):
            _active_oid["value"] = self._oid
            return client.delete(*args, **kwargs)

        def patch(self, *args, **kwargs):
            _active_oid["value"] = self._oid
            return client.patch(*args, **kwargs)

    def _factory(oid: str) -> _UserClient:
        return _UserClient(oid)

    yield _factory

    # Cleanup: remove the override
    app.dependency_overrides.pop(get_current_user, None)
