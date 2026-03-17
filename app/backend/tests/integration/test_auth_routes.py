"""Integration tests for auth-protected routes — ownership checks + user scoping.

Test layer: integration (FastAPI TestClient, in-process, mocked auth).
Uses dependency overrides to inject fixed User objects, verifying that
routes enforce session ownership correctly.

Follows the project's test convention:
    - asyncio_mode = "auto"
    - Markers: @pytest.mark.integration
    - TestClient with InMemorySessionStore + EchoLLMService
"""

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def authenticated_client():
    """TestClient with a mocked authenticated user (test-oid-123).

    Uses FastAPI dependency_overrides to bypass real JWT validation.
    Sets AUTH_ENABLED=true so ownership checks are active.
    Returns a tuple of (client, user) so tests can reference user.oid.

    Clears COSMOS_SESSION_ENDPOINT to avoid Cosmos health checks
    during startup.
    """
    os.environ["LLM_PROVIDER"] = "echo"
    os.environ["OTEL_EXPORT_TARGET"] = ""
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["AUTH_CLIENT_ID"] = "test-client-id"
    os.environ["AUTH_TENANT_ID"] = "common"

    # Prevent Cosmos DB connection attempts during lifespan startup
    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

    # Re-create settings to pick up AUTH_ENABLED=true
    from app.foundation.config import Settings
    test_settings = Settings()

    from app.auth import User, get_current_user
    from app.main import app
    import app.foundation.config as config_mod
    import app.routers.sessions as sessions_mod
    import app.routers.chat as chat_mod
    import app.auth as auth_mod
    from app.services.session_store.memory import InMemorySessionStore
    from app.services.llm import EchoLLMService

    # Patch settings in all modules that check auth_enabled
    original_settings = config_mod.settings
    config_mod.settings = test_settings
    auth_mod.settings = test_settings

    test_user = User(oid="test-oid-123", email="test@example.com", name="Test User")

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.state.store = InMemorySessionStore()
    app.state.llm = EchoLLMService()

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, test_user

    app.dependency_overrides.clear()
    config_mod.settings = original_settings
    auth_mod.settings = original_settings
    # Restore COSMOS_SESSION_ENDPOINT if it was set
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos


@pytest.fixture
def second_user_client():
    """TestClient with a different mocked user (other-oid-456).

    For cross-user isolation tests — verifies User B can't access User A's sessions.
    """
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("OTEL_EXPORT_TARGET", "")

    # Prevent Cosmos DB connection attempts during lifespan startup
    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

    from app.auth import User, get_current_user
    from app.main import app
    from app.services.session_store.memory import InMemorySessionStore
    from app.services.llm import EchoLLMService

    other_user = User(oid="other-oid-456", email="other@example.com", name="Other User")

    async def override_get_current_user():
        return other_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    # NOTE: don't reset app.state.store — share the same store instance
    # so User B can attempt to access User A's sessions.

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, other_user

    app.dependency_overrides.clear()
    # Restore COSMOS_SESSION_ENDPOINT if it was set
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos


def _create_default_session(client):
    """Helper: create a __default__ session by direct store access.

    Uses the TestClient's app.state.store to insert a session with
    user_id='__default__' that should be visible to all users.
    Returns the session object.
    """
    from app.foundation.models import Session
    from app.main import app

    session = Session(title="Default Demo", user_id="__default__")
    # Use sync adapter since TestClient runs in sync context
    import asyncio
    loop = asyncio.new_event_loop()
    loop.run_until_complete(app.state.store.create(session))
    loop.close()
    return session


# ── Tests: Session creation ─────────────────────────────────────────────────


class TestCreateSession:
    """Tests for POST /api/sessions with auth."""

    def test_create_session_sets_user_id(self, authenticated_client):
        """Created session has user_id = authenticated user's oid."""
        client, user = authenticated_client
        res = client.post("/api/sessions", json={"title": "My session"})
        assert res.status_code == 201
        assert res.json()["user_id"] == user.oid


# ── Tests: Session listing + filtering ───────────────────────────────────────


class TestListSessions:
    """Tests for GET /api/sessions with user filtering."""

    def test_list_sessions_shows_own(self, authenticated_client):
        """User sees their own sessions in the list."""
        client, user = authenticated_client
        client.post("/api/sessions", json={"title": "Mine"})
        res = client.get("/api/sessions")
        assert res.status_code == 200
        titles = [s["title"] for s in res.json()]
        assert "Mine" in titles

    def test_list_sessions_filters_other_users(self, authenticated_client):
        """User A's sessions not visible to User B."""
        client_a, user_a = authenticated_client

        # User A creates a session
        res = client_a.post("/api/sessions", json={"title": "A's session"})
        assert res.status_code == 201

        # Now switch to User B
        from app.auth import User, get_current_user
        from app.main import app

        user_b = User(oid="other-oid-456", email="other@example.com", name="Other")

        async def override_b():
            return user_b

        app.dependency_overrides[get_current_user] = override_b

        # User B should NOT see User A's session
        res = client_a.get("/api/sessions")
        assert res.status_code == 200
        titles = [s["title"] for s in res.json()]
        assert "A's session" not in titles

    def test_list_sessions_excludes_defaults_for_authenticated(self, authenticated_client):
        """__default__ sessions are not listed for authenticated users.

        Users get per-user cloned copies of demo conversations via
        automatic seeding — the __default__ originals are hidden.
        """
        client, user = authenticated_client

        _create_default_session(client)

        res = client.get("/api/sessions")
        assert res.status_code == 200
        titles = [s["title"] for s in res.json()]
        assert "Default Demo" not in titles


# ── Tests: Session get + ownership ───────────────────────────────────────────


class TestGetSession:
    """Tests for GET /api/sessions/{id} with ownership checks."""

    def test_get_own_session(self, authenticated_client):
        """User can GET their own session."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "Mine"})
        session_id = res.json()["id"]
        res = client.get(f"/api/sessions/{session_id}")
        assert res.status_code == 200
        assert res.json()["title"] == "Mine"

    def test_get_other_users_session_returns_404(self, authenticated_client):
        """User can't GET another user's session — returns 404."""
        client_a, _ = authenticated_client

        # Create session as User A
        res = client_a.post("/api/sessions", json={"title": "A's private"})
        session_id = res.json()["id"]

        # Switch to User B
        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        res = client_a.get(f"/api/sessions/{session_id}")
        assert res.status_code == 404


# ── Tests: Session update + ownership ────────────────────────────────────────


class TestUpdateSession:
    """Tests for PATCH /api/sessions/{id} with ownership checks."""

    def test_patch_own_session(self, authenticated_client):
        """User can PATCH their own session."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "Old"})
        session_id = res.json()["id"]
        res = client.patch(f"/api/sessions/{session_id}", json={"title": "New"})
        assert res.status_code == 200
        assert res.json()["title"] == "New"

    def test_patch_other_users_session_returns_404(self, authenticated_client):
        """User can't PATCH another user's session — returns 404."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "A's"})
        session_id = res.json()["id"]

        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        res = client.patch(f"/api/sessions/{session_id}", json={"title": "Hacked"})
        assert res.status_code == 404

    def test_patch_default_session_returns_403(self, authenticated_client):
        """User can't modify a __default__ session — returns 403."""
        client, _ = authenticated_client

        default_session = _create_default_session(client)

        res = client.patch(
            f"/api/sessions/{default_session.id}", json={"title": "Renamed"}
        )
        assert res.status_code == 403


# ── Tests: Session delete + ownership ────────────────────────────────────────


class TestDeleteSession:
    """Tests for DELETE /api/sessions/{id} with ownership checks."""

    def test_delete_own_session(self, authenticated_client):
        """User can DELETE their own session."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "Doomed"})
        session_id = res.json()["id"]
        res = client.delete(f"/api/sessions/{session_id}")
        assert res.status_code == 204

    def test_delete_other_users_session_returns_404(self, authenticated_client):
        """User can't DELETE another user's session — returns 404."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "A's"})
        session_id = res.json()["id"]

        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        res = client.delete(f"/api/sessions/{session_id}")
        assert res.status_code == 404

    def test_delete_default_session_returns_403(self, authenticated_client):
        """User can't delete a __default__ session — returns 403."""
        client, _ = authenticated_client

        default_session = _create_default_session(client)

        res = client.delete(f"/api/sessions/{default_session.id}")
        assert res.status_code == 403


# ── Tests: Chat + ownership ──────────────────────────────────────────────────


class TestChatOwnership:
    """Tests for POST /api/chat/{id} with ownership checks."""

    def test_chat_own_session(self, authenticated_client):
        """User can chat in their own session."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "Chat test"})
        session_id = res.json()["id"]
        res = client.post(
            f"/api/chat/{session_id}",
            json={"content": "Hello"},
            headers={"Accept": "text/event-stream"},
        )
        assert res.status_code == 200

    def test_chat_other_users_session_returns_404(self, authenticated_client):
        """User can't chat in another user's session — returns 404."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "A's chat"})
        session_id = res.json()["id"]

        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        res = client.post(
            f"/api/chat/{session_id}",
            json={"content": "Hello"},
            headers={"Accept": "text/event-stream"},
        )
        assert res.status_code == 404


# ── Tests: Save + ownership ──────────────────────────────────────────────────


class TestSaveOwnership:
    """Tests for POST /api/sessions/{id}/save with ownership checks."""

    def test_save_other_users_session_returns_404(self, authenticated_client):
        """User can't save another user's session — returns 404."""
        client, _ = authenticated_client
        res = client.post("/api/sessions", json={"title": "A's saveable"})
        session_id = res.json()["id"]

        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        res = client.post(f"/api/sessions/{session_id}/save")
        assert res.status_code == 404


# ── Tests: Abort + ownership ─────────────────────────────────────────────────


class TestAbortOwnership:
    """Tests for POST /api/chat/{id}/abort with ownership checks."""

    def test_abort_other_users_session_returns_404(self, authenticated_client):
        """User can't abort another user's stream — returns 404."""
        client, _ = authenticated_client
        # Create a session as User A
        res = client.post("/api/sessions", json={"title": "A's stream"})
        session_id = res.json()["id"]

        from app.auth import User, get_current_user
        from app.main import app

        async def override_b():
            return User(oid="other-oid-456", email="b@b.com", name="B")

        app.dependency_overrides[get_current_user] = override_b

        # User B tries to abort User A's session — should get 404
        # (even though no active generation exists, ownership check should run first)
        res = client.post(f"/api/chat/{session_id}/abort")
        assert res.status_code == 404


# ── Tests: Reset defaults ───────────────────────────────────────────────────


class TestResetDefaults:
    """Tests for POST /api/sessions/reset-defaults."""

    def test_reset_defaults_reseeds_demo_conversations(self, authenticated_client):
        """After reset, user gets fresh copies of demo conversations."""
        client, user = authenticated_client

        from app.main import app

        # Set up a __default__ template and register it
        default = _create_default_session(client)
        app.state.store._template_ids = [default.id]

        # First list triggers auto-seed — user gets a clone
        res = client.get("/api/sessions")
        assert res.status_code == 200
        sessions_before = res.json()
        demo_titles = [s["title"] for s in sessions_before if s["title"] == "Default Demo"]
        assert len(demo_titles) == 1

        # Reset defaults
        res = client.post("/api/sessions/reset-defaults")
        assert res.status_code == 200
        body = res.json()
        assert body["deleted"] >= 1
        assert body["seeded"] >= 1

        # Verify user still has a "Default Demo" — it's a fresh clone
        res = client.get("/api/sessions")
        assert res.status_code == 200
        sessions_after = res.json()
        demo_after = [s for s in sessions_after if s["title"] == "Default Demo"]
        assert len(demo_after) == 1
        # Fresh clone has a new ID
        demo_id_before = [s["id"] for s in sessions_before if s["title"] == "Default Demo"][0]
        assert demo_after[0]["id"] != demo_id_before
