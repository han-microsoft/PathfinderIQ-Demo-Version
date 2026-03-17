"""Integration tests for session user_id scoping.

Test layer: integration (FastAPI TestClient, in-process).
Verifies that InMemorySessionStore correctly filters sessions by user_id
and that the Session model round-trips user_id through the API.

Follows the project's test convention:
    - asyncio_mode = "auto"
    - Markers: @pytest.mark.integration
    - Uses the existing ``client`` fixture
"""

import pytest

pytestmark = pytest.mark.integration


class TestInMemoryStoreUserIdFiltering:
    """Verify InMemorySessionStore.list_all() filters by user_id."""

    async def test_list_all_unfiltered_returns_all(self):
        """list_all() with no user_id returns all sessions."""
        from app.services.session_store.memory import InMemorySessionStore
        from app.foundation.models import Session

        store = InMemorySessionStore()
        await store.create(Session(title="A", user_id="user-1"))
        await store.create(Session(title="B", user_id="user-2"))
        await store.create(Session(title="C", user_id="__default__"))

        result = await store.list_all()
        assert len(result) == 3

    async def test_list_all_excludes_default_and_other_users(self):
        """list_all(user_id='user-1') returns only user-1's sessions.

        __default__ and other users' sessions are excluded. Users get
        cloned copies of templates via _ensure_user_seeded(), so the
        originals are never returned.
        """
        from app.services.session_store.memory import InMemorySessionStore
        from app.foundation.models import Session

        store = InMemorySessionStore()
        await store.create(Session(title="Mine", user_id="user-1"))
        await store.create(Session(title="Other", user_id="user-2"))
        await store.create(Session(title="Default", user_id="__default__"))

        result = await store.list_all(user_id="user-1")
        titles = {s.title for s in result}
        assert titles == {"Mine"}

    async def test_list_all_excludes_legacy_empty_user_id(self):
        """list_all(user_id='x') excludes sessions with empty user_id (legacy)."""
        from app.services.session_store.memory import InMemorySessionStore
        from app.foundation.models import Session

        store = InMemorySessionStore()
        await store.create(Session(title="Legacy", user_id=""))
        await store.create(Session(title="Mine", user_id="user-1"))

        result = await store.list_all(user_id="user-1")
        titles = {s.title for s in result}
        assert titles == {"Mine"}

    async def test_summary_contains_user_id(self):
        """SessionSummary from list_all() includes user_id field."""
        from app.services.session_store.memory import InMemorySessionStore
        from app.foundation.models import Session

        store = InMemorySessionStore()
        await store.create(Session(title="Test", user_id="oid-abc"))

        result = await store.list_all()
        assert len(result) == 1
        assert result[0].user_id == "oid-abc"


class TestSessionApiUserIdField:
    """Verify user_id round-trips through the session API."""

    def test_created_session_has_user_id_from_auth(self, client):
        """POST /sessions sets user_id from get_current_user.

        With AUTH_ENABLED=false (default), get_current_user returns
        User(oid='anonymous'), so user_id='anonymous'.
        """
        res = client.post("/api/sessions", json={"title": "test"})
        assert res.status_code == 201
        body = res.json()
        assert "user_id" in body
        # Anonymous user when auth is disabled
        assert body["user_id"] == "anonymous"

    def test_get_session_includes_user_id(self, client):
        """GET /sessions/{id} response includes user_id field."""
        res = client.post("/api/sessions", json={"title": "test"})
        session_id = res.json()["id"]
        res = client.get(f"/api/sessions/{session_id}")
        assert res.status_code == 200
        assert "user_id" in res.json()

    def test_list_sessions_includes_user_id(self, client):
        """GET /sessions returns summaries with user_id field."""
        client.post("/api/sessions", json={"title": "test"})
        res = client.get("/api/sessions")
        assert res.status_code == 200
        for summary in res.json():
            assert "user_id" in summary
