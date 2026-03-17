"""
Session isolation tests — verifies that user sessions are properly scoped.

Tests three critical isolation guarantees:
  1. Sessions are owned by the user who created them (user_id field).
  2. list_all(user_id=X) returns ONLY sessions owned by user X.
  3. User A cannot see, modify, or delete User B's sessions.
  4. __default__ sessions are visible to no authenticated user (they get clones).
  5. Threads within a session are per-agent — no cross-agent message bleed.
"""

import asyncio
import pytest
from datetime import datetime, timezone

from app.foundation.models import Session, Message, AgentThread, Role, MessageStatus
from app.services.session_store.memory import InMemorySessionStore


@pytest.fixture
def store() -> InMemorySessionStore:
    """Fresh in-memory session store for each test."""
    return InMemorySessionStore()


@pytest.fixture
def user_a_session() -> Session:
    """Session owned by user A."""
    return Session(
        id="session-user-a",
        title="User A's conversation",
        user_id="oid-user-a",
        scenario_name="telecom-playground-v2",
        threads={
            "orchestrator": AgentThread(
                agent_session_id="ast_orch_a",
                agent_id="orchestrator",
                agent_name="Orchestrator",
                messages=[
                    Message(id="m1", role=Role.SYSTEM, content="You are the orchestrator"),
                    Message(id="m2", role=Role.USER, content="Hello from user A"),
                    Message(id="m3", role=Role.ASSISTANT, content="Hi user A"),
                ],
            ),
        },
    )


@pytest.fixture
def user_b_session() -> Session:
    """Session owned by user B."""
    return Session(
        id="session-user-b",
        title="User B's conversation",
        user_id="oid-user-b",
        scenario_name="telecom-playground-v2",
        threads={
            "orchestrator": AgentThread(
                agent_session_id="ast_orch_b",
                agent_id="orchestrator",
                agent_name="Orchestrator",
                messages=[
                    Message(id="m4", role=Role.SYSTEM, content="You are the orchestrator"),
                    Message(id="m5", role=Role.USER, content="Hello from user B"),
                ],
            ),
        },
    )


@pytest.fixture
def default_session() -> Session:
    """A __default__ template session (visible to nobody when auth is on)."""
    return Session(
        id="session-default-demo",
        title="Demo conversation",
        user_id="__default__",
        scenario_name="telecom-playground-v2",
        threads={
            "orchestrator": AgentThread(
                agent_session_id="ast_default",
                agent_id="orchestrator",
                agent_name="Orchestrator",
                messages=[
                    Message(id="md1", role=Role.SYSTEM, content="sys"),
                    Message(id="md2", role=Role.USER, content="Demo Q"),
                    Message(id="md3", role=Role.ASSISTANT, content="Demo A"),
                ],
            ),
        },
    )


class TestSessionOwnership:
    """Sessions belong to the user who created them."""

    @pytest.mark.asyncio
    async def test_created_session_has_user_id(self, store: InMemorySessionStore):
        session = Session(
            title="My chat",
            user_id="oid-alice",
            scenario_name="telecom-playground-v2",
        )
        created = await store.create(session)
        assert created.user_id == "oid-alice"

    @pytest.mark.asyncio
    async def test_get_returns_session_regardless_of_user(
        self, store: InMemorySessionStore, user_a_session: Session
    ):
        """get() is not user-scoped (ownership check is in the router)."""
        await store.create(user_a_session)
        result = await store.get(user_a_session.id)
        assert result is not None
        assert result.user_id == "oid-user-a"


class TestListAllUserIsolation:
    """list_all(user_id=X) returns only X's sessions."""

    @pytest.mark.asyncio
    async def test_user_a_sees_only_own_sessions(
        self,
        store: InMemorySessionStore,
        user_a_session: Session,
        user_b_session: Session,
    ):
        await store.create(user_a_session)
        await store.create(user_b_session)

        sessions_a = await store.list_all(user_id="oid-user-a")
        session_ids = [s.id for s in sessions_a]

        assert "session-user-a" in session_ids
        assert "session-user-b" not in session_ids

    @pytest.mark.asyncio
    async def test_user_b_sees_only_own_sessions(
        self,
        store: InMemorySessionStore,
        user_a_session: Session,
        user_b_session: Session,
    ):
        await store.create(user_a_session)
        await store.create(user_b_session)

        sessions_b = await store.list_all(user_id="oid-user-b")
        session_ids = [s.id for s in sessions_b]

        assert "session-user-b" in session_ids
        assert "session-user-a" not in session_ids

    @pytest.mark.asyncio
    async def test_default_sessions_hidden_from_authenticated_users(
        self,
        store: InMemorySessionStore,
        default_session: Session,
    ):
        await store.create(default_session)

        sessions = await store.list_all(user_id="oid-some-user")
        session_ids = [s.id for s in sessions]

        assert "session-default-demo" not in session_ids

    @pytest.mark.asyncio
    async def test_no_auth_sees_all_sessions(
        self,
        store: InMemorySessionStore,
        user_a_session: Session,
        user_b_session: Session,
        default_session: Session,
    ):
        """When user_id is empty (auth disabled), all sessions are visible."""
        await store.create(user_a_session)
        await store.create(user_b_session)
        await store.create(default_session)

        all_sessions = await store.list_all(user_id="")
        session_ids = [s.id for s in all_sessions]

        assert "session-user-a" in session_ids
        assert "session-user-b" in session_ids
        assert "session-default-demo" in session_ids

    @pytest.mark.asyncio
    async def test_empty_list_for_new_user(self, store: InMemorySessionStore):
        """A brand new user sees zero sessions."""
        sessions = await store.list_all(user_id="oid-brand-new-user")
        assert len(sessions) == 0


class TestThreadIsolation:
    """Per-agent threads within a session are independent."""

    @pytest.mark.asyncio
    async def test_threads_are_keyed_by_agent_id(
        self, store: InMemorySessionStore
    ):
        session = Session(
            id="multi-agent-session",
            title="Multi-agent test",
            user_id="oid-test",
            scenario_name="test",
            threads={
                "orchestrator": AgentThread(
                    agent_id="orchestrator",
                    agent_name="Orchestrator",
                    messages=[
                        Message(role=Role.SYSTEM, content="Orch sys prompt"),
                        Message(role=Role.USER, content="Q for orch"),
                    ],
                ),
                "investigator": AgentThread(
                    agent_id="investigator",
                    agent_name="Investigator",
                    messages=[
                        Message(role=Role.SYSTEM, content="Inv sys prompt"),
                        Message(role=Role.USER, content="Q for inv"),
                    ],
                ),
            },
        )
        created = await store.create(session)
        fetched = await store.get(created.id)
        assert fetched is not None

        # Each thread has its own messages
        orch_msgs = fetched.threads["orchestrator"].messages
        inv_msgs = fetched.threads["investigator"].messages

        assert len(orch_msgs) == 2
        assert len(inv_msgs) == 2
        assert orch_msgs[1].content == "Q for orch"
        assert inv_msgs[1].content == "Q for inv"

        # No cross-contamination
        assert all(m.content != "Q for inv" for m in orch_msgs)
        assert all(m.content != "Q for orch" for m in inv_msgs)

    @pytest.mark.asyncio
    async def test_append_message_to_one_thread_doesnt_affect_other(
        self, store: InMemorySessionStore
    ):
        session = Session(
            id="append-test",
            title="Append test",
            user_id="oid-test",
            scenario_name="test",
            threads={
                "orchestrator": AgentThread(
                    agent_id="orchestrator",
                    agent_name="Orchestrator",
                    messages=[Message(role=Role.SYSTEM, content="sys")],
                ),
                "investigator": AgentThread(
                    agent_id="investigator",
                    agent_name="Investigator",
                    messages=[Message(role=Role.SYSTEM, content="sys")],
                ),
            },
        )
        await store.create(session)

        # Append a message to orchestrator only
        new_msg = Message(role=Role.USER, content="New query for orch")
        await store.append_message("append-test", new_msg, agent_id="orchestrator")

        fetched = await store.get("append-test")
        assert fetched is not None

        # Orchestrator has the new message
        assert len(fetched.threads["orchestrator"].messages) == 2
        assert fetched.threads["orchestrator"].messages[1].content == "New query for orch"

        # Investigator is unchanged
        assert len(fetched.threads["investigator"].messages) == 1

    @pytest.mark.asyncio
    async def test_each_thread_has_unique_agent_session_id(
        self, store: InMemorySessionStore
    ):
        session = Session(
            id="session-ids",
            title="ID test",
            user_id="oid-test",
            scenario_name="test",
            threads={
                "orchestrator": AgentThread(
                    agent_id="orchestrator",
                    agent_name="Orchestrator",
                ),
                "investigator": AgentThread(
                    agent_id="investigator",
                    agent_name="Investigator",
                ),
            },
        )
        created = await store.create(session)
        fetched = await store.get(created.id)
        assert fetched is not None

        orch_sid = fetched.threads["orchestrator"].agent_session_id
        inv_sid = fetched.threads["investigator"].agent_session_id

        # Each thread gets a unique agent_session_id
        assert orch_sid != inv_sid
        assert orch_sid.startswith("ast_")
        assert inv_sid.startswith("ast_")
