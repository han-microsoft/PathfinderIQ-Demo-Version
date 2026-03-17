"""Tests for InMemorySessionStore thread-aware methods.

Covers:
    - append_message creates thread on first append
    - append_message adds to existing thread
    - append_message defaults empty agent_id to "orchestrator"
    - update_message replaces message by ID within a thread
    - get_thread returns thread or None
    - create_thread with and without system prompt
    - create_thread raises KeyError for missing session
"""

import asyncio

import pytest

from app.foundation.models import AgentThread, Message, Role, Session
from app.services.session_store.memory import InMemorySessionStore


@pytest.fixture
def store() -> InMemorySessionStore:
    """Fresh in-memory store for each test."""
    return InMemorySessionStore()


@pytest.fixture
def session() -> Session:
    """A bare session with a known ID."""
    return Session(id="test_session_01", title="Test Session")


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestAppendMessage:
    """append_message: requires thread to exist, appends messages."""

    def test_raises_on_missing_thread(self, store, session):
        """append_message raises KeyError when thread doesn't exist."""
        _run(store.create(session))
        msg = Message(role=Role.USER, content="hello")
        with pytest.raises(KeyError, match="Thread.*not found"):
            _run(store.append_message("test_session_01", msg, agent_id="orchestrator"))

    def test_appends_after_create_thread(self, store, session):
        """append_message works after create_thread provides the thread."""
        _run(store.create(session))
        _run(store.create_thread("test_session_01", "orchestrator", "Orchestrator", "system prompt"))
        msg = Message(role=Role.USER, content="hello")
        _run(store.append_message("test_session_01", msg, agent_id="orchestrator"))

        result = _run(store.get("test_session_01"))
        assert "orchestrator" in result.threads
        # system prompt + user message = 2
        assert len(result.threads["orchestrator"].messages) == 2
        assert result.threads["orchestrator"].messages[1].content == "hello"

    def test_appends_to_existing_thread(self, store, session):
        """Subsequent appends add to the same thread."""
        _run(store.create(session))
        _run(store.create_thread("test_session_01", "orch", "Orch", "prompt"))
        _run(store.append_message("test_session_01", Message(role=Role.ASSISTANT, content="second"), agent_id="orch"))

        result = _run(store.get("test_session_01"))
        assert len(result.threads["orch"].messages) == 2

    def test_empty_agent_id_defaults_to_orchestrator(self, store, session):
        """Empty agent_id falls back to 'orchestrator'."""
        _run(store.create(session))
        _run(store.create_thread("test_session_01", "orchestrator", "Orchestrator", ""))
        _run(store.append_message("test_session_01", Message(role=Role.USER, content="q")))

        result = _run(store.get("test_session_01"))
        assert "orchestrator" in result.threads

    def test_raises_on_missing_session(self, store):
        """KeyError raised when session_id doesn't exist."""
        with pytest.raises(KeyError):
            _run(store.append_message("nonexistent", Message(role=Role.USER, content="x")))


class TestUpdateMessage:
    """update_message: replaces message by ID."""

    def test_replaces_message_content(self, store, session):
        """Message is updated in-place by matching ID."""
        _run(store.create(session))
        _run(store.create_thread("test_session_01", "orch", "Orch", ""))
        original = Message(id="msg_upd", role=Role.ASSISTANT, content="streaming...")
        _run(store.append_message("test_session_01", original, agent_id="orch"))

        updated = Message(id="msg_upd", role=Role.ASSISTANT, content="final answer")
        _run(store.update_message("test_session_01", updated, agent_id="orch"))

        result = _run(store.get("test_session_01"))
        assert result.threads["orch"].messages[0].content == "final answer"


class TestGetThread:
    """get_thread: retrieves a single agent thread."""

    def test_returns_thread(self, store, session):
        """Returns the AgentThread when it exists."""
        _run(store.create(session))
        _run(store.create_thread("test_session_01", "net_inv", "NetInv", ""))
        _run(store.append_message("test_session_01", Message(role=Role.USER, content="q"), agent_id="net_inv"))

        thread = _run(store.get_thread("test_session_01", "net_inv"))
        assert thread is not None
        assert thread.agent_id == "net_inv"

    def test_returns_none_for_missing_thread(self, store, session):
        """Returns None when the agent_id doesn't have a thread."""
        _run(store.create(session))
        assert _run(store.get_thread("test_session_01", "nonexistent")) is None

    def test_returns_none_for_missing_session(self, store):
        """Returns None when the session doesn't exist."""
        assert _run(store.get_thread("no_session", "orch")) is None


class TestCreateThread:
    """create_thread: creates a new AgentThread in a session."""

    def test_creates_thread_without_system_prompt(self, store, session):
        """Thread created with no system prompt has zero messages."""
        _run(store.create(session))
        thread = _run(store.create_thread("test_session_01", "analyzer", "LogAnalyzer"))

        assert isinstance(thread, AgentThread)
        assert thread.agent_id == "analyzer"
        assert thread.agent_name == "LogAnalyzer"
        assert len(thread.messages) == 0

    def test_creates_thread_with_system_prompt(self, store, session):
        """System prompt stored as message 0 with role=system."""
        _run(store.create(session))
        thread = _run(store.create_thread(
            "test_session_01", "orch", "Orchestrator", system_prompt="You are helpful."
        ))

        assert len(thread.messages) == 1
        assert thread.messages[0].role == Role.SYSTEM
        assert thread.messages[0].content == "You are helpful."

    def test_raises_on_missing_session(self, store):
        """KeyError raised when session doesn't exist."""
        with pytest.raises(KeyError):
            _run(store.create_thread("nonexistent", "orch", "Orchestrator"))
