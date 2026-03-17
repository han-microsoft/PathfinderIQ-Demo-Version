"""Unit tests for per-user demo conversation seeding.

Validates that InMemorySessionStore correctly clones __default__
template sessions for new users on first list_all() call.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python -m pytest tests/unit/test_user_seeding.py -v
"""

import pytest

from app.foundation.models import AgentThread, Message, Role, Session


# ── Helpers ────────────────────────────────────────────────────────────────────


def _all_messages(session: Session) -> list[Message]:
    """Get all messages across all threads in a session (v3 format)."""
    msgs = []
    for thread in session.threads.values():
        msgs.extend(thread.messages)
    return msgs


def _make_template(title: str, msg_count: int = 2) -> Session:
    """Build a __default__ template session with N stub messages in a thread."""
    messages = [
        Message(
            role=Role.USER if i % 2 == 0 else Role.ASSISTANT,
            content=f"Message {i} of {title}",
        )
        for i in range(msg_count)
    ]
    # Build a v3-format session with messages in an orchestrator thread
    from app.foundation.models import AgentThread
    session = Session(
        title=title,
        user_id="__default__",
        scenario_name="test-scenario",
    )
    session.threads["orchestrator"] = AgentThread(
        agent_id="orchestrator",
        agent_name="orchestrator",
        messages=messages,
    )
    return session


# ── Tests ────────────────────────────────────────────────────────────────────


class TestUserSeedingMemory:
    """Verify InMemorySessionStore._ensure_user_seeded() cloning behavior."""

    async def test_first_list_clones_templates_for_user(self):
        """First list_all(user_id=X) clones all template sessions."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()

        # Simulate startup: create __default__ templates + register their IDs
        t1 = _make_template("Fibre Cut")
        t2 = _make_template("Wear and Tear")
        await store.create(t1)
        await store.create(t2)
        store._template_ids = [t1.id, t2.id]

        # First list_all for a new user triggers seeding
        result = await store.list_all(user_id="user-abc")

        # User should see 2 cloned sessions, not the __default__ originals
        assert len(result) == 2
        titles = {s.title for s in result}
        assert titles == {"Fibre Cut", "Wear and Tear"}
        # Clones have user-abc as owner, not __default__
        for s in result:
            assert s.user_id == "user-abc"

    async def test_cloned_sessions_have_new_ids(self):
        """Cloned sessions must have different IDs from templates."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        result = await store.list_all(user_id="user-xyz")
        assert len(result) == 1
        # Clone ID must differ from template ID
        assert result[0].id != t1.id

    async def test_cloned_messages_have_new_ids(self):
        """Cloned messages must have different IDs from template messages."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo", msg_count=3)
        await store.create(t1)
        store._template_ids = [t1.id]

        # Seed and retrieve the clone
        await store.list_all(user_id="user-xyz")
        # Find the cloned session
        cloned = [
            s for s in store._sessions.values()
            if s.user_id == "user-xyz"
        ]
        assert len(cloned) == 1
        clone = cloned[0]

        # Every message ID must differ from the template's message IDs
        template_msg_ids = {m.id for m in _all_messages(t1)}
        clone_msg_ids = {m.id for m in _all_messages(clone)}
        assert template_msg_ids.isdisjoint(clone_msg_ids)
        # Content must match
        for orig, cloned_msg in zip(_all_messages(t1), _all_messages(clone)):
            assert cloned_msg.content == orig.content
            assert cloned_msg.role == orig.role

    async def test_seeding_is_idempotent(self):
        """Multiple list_all calls don't create duplicate clones."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        # Call list_all three times for the same user
        await store.list_all(user_id="user-1")
        await store.list_all(user_id="user-1")
        await store.list_all(user_id="user-1")

        # Should still have exactly 1 clone (plus the template)
        user_sessions = [
            s for s in store._sessions.values()
            if s.user_id == "user-1"
        ]
        assert len(user_sessions) == 1

    async def test_different_users_get_separate_clones(self):
        """Each user gets their own independent clones."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        r1 = await store.list_all(user_id="alice")
        r2 = await store.list_all(user_id="bob")

        assert len(r1) == 1
        assert len(r2) == 1
        # Each user has their own clone with a distinct ID
        assert r1[0].id != r2[0].id
        assert r1[0].user_id == "alice"
        assert r2[0].user_id == "bob"

    async def test_no_templates_no_seeding(self):
        """When no templates exist, no clones are created."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        # _template_ids is empty by default

        result = await store.list_all(user_id="user-1")
        assert len(result) == 0

    async def test_user_with_own_sessions_not_reseeded(self):
        """Users who already have sessions don't get re-seeded."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        # User already has a session (e.g., created one manually)
        await store.create(Session(title="My Own", user_id="user-1"))

        result = await store.list_all(user_id="user-1")
        titles = {s.title for s in result}
        # Should have only the manually-created session, no clone
        assert titles == {"My Own"}

    async def test_auth_disabled_returns_all_including_default(self):
        """list_all() with no user_id returns all sessions (auth disabled)."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]
        await store.create(Session(title="User Session", user_id="user-1"))

        result = await store.list_all()  # no user_id — auth disabled
        titles = {s.title for s in result}
        assert "Demo" in titles
        assert "User Session" in titles

    async def test_cloned_sessions_are_mutable(self):
        """Users can modify their cloned sessions (rename, delete)."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        # Seed
        result = await store.list_all(user_id="user-1")
        clone_id = result[0].id

        # Rename the clone — should succeed
        clone = await store.get(clone_id)
        clone.title = "My Renamed Demo"
        await store.update(clone)

        updated = await store.get(clone_id)
        assert updated.title == "My Renamed Demo"

        # Delete the clone — should succeed
        deleted = await store.delete(clone_id)
        assert deleted is True

        # Template still exists
        template = await store.get(t1.id)
        assert template is not None
        assert template.title == "Demo"

    async def test_cloned_messages_preserve_tool_calls(self):
        """Cloned messages preserve tool_calls from templates."""
        from app.services.session_store.memory import InMemorySessionStore
        from app.foundation.models import ToolCall

        store = InMemorySessionStore()
        tc = ToolCall(name="query_graph", arguments={"q": "test"}, result="data")
        msg = Message(
            role=Role.ASSISTANT,
            content="Result",
            tool_calls=[tc],
        )
        t1 = Session(
            title="With Tools",
            user_id="__default__",
        )
        t1.threads["orchestrator"] = AgentThread(
            agent_id="orchestrator",
            agent_name="orchestrator",
            messages=[msg],
        )
        await store.create(t1)
        store._template_ids = [t1.id]

        # Seed and check clone
        await store.list_all(user_id="user-1")
        clones = [s for s in store._sessions.values() if s.user_id == "user-1"]
        assert len(clones) == 1
        clone_msgs = _all_messages(clones[0])
        assert len(clone_msgs) == 1
        assert len(clone_msgs[0].tool_calls) == 1
        assert clone_msgs[0].tool_calls[0].name == "query_graph"
        assert clone_msgs[0].tool_calls[0].result == "data"


class TestResetDefaults:
    """Verify that clearing seeded_users cache allows re-seeding."""

    async def test_reseed_after_cache_clear(self):
        """Clearing _seeded_users and deleting clones triggers fresh clones."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        # First seed
        r1 = await store.list_all(user_id="user-1")
        assert len(r1) == 1
        first_clone_id = r1[0].id

        # Delete clones and clear seeded cache (simulates reset-defaults)
        await store.delete(first_clone_id)
        store._seeded_users.discard("user-1")

        # Second list_all re-seeds
        r2 = await store.list_all(user_id="user-1")
        assert len(r2) == 1
        # New clone has a different ID
        assert r2[0].id != first_clone_id
        assert r2[0].title == "Demo"
        assert r2[0].user_id == "user-1"

    async def test_reseed_preserves_manually_created_sessions(self):
        """Reset-defaults only deletes template clones, not user's own sessions."""
        from app.services.session_store.memory import InMemorySessionStore

        store = InMemorySessionStore()
        t1 = _make_template("Demo")
        await store.create(t1)
        store._template_ids = [t1.id]

        # Seed templates
        await store.list_all(user_id="user-1")
        # User creates their own session
        own = Session(title="My Own Work", user_id="user-1")
        await store.create(own)

        # Simulate reset: delete template clones (by title match), keep own
        all_user = await store.list_all(user_id="user-1")
        for s in all_user:
            if s.title == "Demo":
                await store.delete(s.id)

        store._seeded_users.discard("user-1")

        # Re-list triggers reseed — but user already has sessions so
        # _ensure_user_seeded skips. Force it by clearing cache.
        r = await store.list_all(user_id="user-1")
        titles = {s.title for s in r}
        # "My Own Work" should survive regardless
        assert "My Own Work" in titles
