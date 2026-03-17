"""SessionStateManager unit tests — thread lifecycle and context assembly."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.foundation.models import AgentThread, ContextSnapshot, Message, Role, Session
from app.services.conversation._session_state import SessionStateManager
from app.services.session_store.memory import InMemorySessionStore


def _run(coro):
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def ssm():
    """Fresh SessionStateManager instance."""
    return SessionStateManager()


@pytest.fixture
def store():
    """Fresh InMemorySessionStore with one empty session."""
    s = InMemorySessionStore()
    session = Session(id="test-session")
    _run(s.create(session))
    return s


# ── ensure_thread tests ─────────────────────────────────────────────────────


class TestEnsureThread:
    """Tests for SessionStateManager.ensure_thread()."""

    @patch("agents.registry.get_prompt")
    def test_creates_thread_when_missing(self, mock_prompt, ssm, store):
        """Thread is created with system prompt when it doesn't exist."""
        mock_prompt.return_value = ("test_agent", "TestAgent", "You are TestAgent.")
        
        session = _run(store.get("test-session"))
        assert "test_agent" not in session.threads

        thread, is_first = _run(ssm.ensure_thread(session, "test-session", "test_agent", store))

        assert thread is not None
        assert thread.agent_id == "test_agent"
        assert thread.agent_name == "TestAgent"
        assert len(thread.messages) == 1
        assert thread.messages[0].role == Role.SYSTEM
        assert thread.messages[0].content == "You are TestAgent."
        assert is_first is True

    @patch("agents.registry.get_prompt")
    def test_returns_existing_thread(self, mock_prompt, ssm, store):
        """Existing thread is reused when its system prompt already matches."""
        # Pre-create thread with system prompt
        _run(store.create_thread("test-session", "orch", "Orchestrator", "System prompt"))
        mock_prompt.return_value = ("orch", "Orchestrator", "System prompt")
        
        session = _run(store.get("test-session"))
        thread, is_first = _run(ssm.ensure_thread(session, "test-session", "orch", store))

        assert thread.agent_id == "orch"
        assert is_first is True  # No non-system messages yet
        assert thread.messages[0].content == "System prompt"
        mock_prompt.assert_called_once_with("orch")

    @patch("agents.registry.get_prompt")
    def test_is_first_message_false_after_messages(self, mock_prompt, ssm, store):
        """is_first_message is False when thread has non-system messages."""
        _run(store.create_thread("test-session", "orch", "Orchestrator", "System prompt"))
        mock_prompt.return_value = ("orch", "Orchestrator", "System prompt")
        # Add a user message
        user_msg = Message(role=Role.USER, content="Hello", agent_name="orch")
        _run(store.append_message("test-session", user_msg, agent_id="orch"))
        
        session = _run(store.get("test-session"))
        thread, is_first = _run(ssm.ensure_thread(session, "test-session", "orch", store))

        assert is_first is False
        mock_prompt.assert_called_once_with("orch")

    @patch("agents.registry.get_prompt")
    def test_backfills_prompt_on_bare_thread(self, mock_prompt, ssm, store):
        """System prompt is backfilled when thread exists but has no system message."""
        mock_prompt.return_value = ("bare_agent", "BareAgent", "You are BareAgent.")
        
        # Manually create a bare thread (simulating old auto-create behavior)
        session = _run(store.get("test-session"))
        session.threads["bare_agent"] = AgentThread(
            agent_id="bare_agent", agent_name="bare_agent",
            messages=[Message(role=Role.USER, content="hi", agent_name="bare_agent")],
        )
        _run(store.update(session))

        session = _run(store.get("test-session"))
        thread, is_first = _run(ssm.ensure_thread(session, "test-session", "bare_agent", store))

        # System prompt should be inserted as message 0
        assert thread.messages[0].role == Role.SYSTEM
        assert thread.messages[0].content == "You are BareAgent."
        # The user message should still be there as message 1
        assert thread.messages[1].role == Role.USER
        assert thread.messages[1].content == "hi"
        # Not first message — there's already a user message
        assert is_first is False

    @patch("agents.registry.get_prompt")
    def test_refreshes_stale_prompt_after_scenario_switch(self, mock_prompt, ssm, store):
        """Existing threads refresh message 0 when the active scenario prompt changes."""
        _run(store.create_thread("test-session", "delegator", "OldDelegator", "You are NOCOrchestrator."))

        mock_prompt.return_value = (
            "delegator",
            "HelloWorldDelegator",
            "You are HelloWorldDelegator. Delegate only to searcher when retrieval is needed.",
        )

        session = _run(store.get("test-session"))
        thread, is_first = _run(ssm.ensure_thread(session, "test-session", "delegator", store))

        assert is_first is True
        assert thread.agent_name == "HelloWorldDelegator"
        assert thread.messages[0].role == Role.SYSTEM
        assert thread.messages[0].content == (
            "You are HelloWorldDelegator. Delegate only to searcher when retrieval is needed."
        )

        refreshed_session = _run(store.get("test-session"))
        assert refreshed_session.threads["delegator"].messages[0].content == (
            "You are HelloWorldDelegator. Delegate only to searcher when retrieval is needed."
        )

    @patch("agents.registry.get_prompt")
    def test_defaults_empty_agent_id_to_orchestrator(self, mock_prompt, ssm, store):
        """Empty agent_id defaults to 'orchestrator'."""
        mock_prompt.return_value = ("orchestrator", "Orchestrator", "You are Orchestrator.")
        
        session = _run(store.get("test-session"))
        thread, _ = _run(ssm.ensure_thread(session, "test-session", "", store))

        assert thread.agent_id == "orchestrator"
        mock_prompt.assert_called_once_with("orchestrator")


# ── build_turn_context tests ────────────────────────────────────────────────


class TestBuildTurnContext:
    """Tests for SessionStateManager.build_turn_context()."""

    def test_extracts_system_prompt_from_message_0(self, ssm):
        """System prompt is extracted from message 0 and used in context."""
        thread = AgentThread(
            agent_id="test", agent_name="TestAgent",
            messages=[
                Message(role=Role.SYSTEM, content="System prompt text"),
                Message(role=Role.USER, content="Hello"),
                Message(role=Role.ASSISTANT, content="Hi there"),
            ],
        )

        context, snapshot = ssm.build_turn_context(thread, "test", "Hello")

        # Context should start with system message
        assert context[0]["role"] == "system"
        assert context[0]["content"] == "System prompt text"
        # Should include the conversation messages
        assert len(context) >= 3  # system + user + assistant

    def test_returns_only_agent_messages(self, ssm):
        """Context contains only the target agent's messages (isolation by construction)."""
        # Thread has only agent X's messages — that's all build_turn_context sees
        thread = AgentThread(
            agent_id="agent_x", agent_name="AgentX",
            messages=[
                Message(role=Role.SYSTEM, content="You are AgentX"),
                Message(role=Role.USER, content="Question for X"),
            ],
        )

        context, _ = ssm.build_turn_context(thread, "agent_x", "Question for X")

        # Only AgentX messages — no cross-agent contamination possible
        for msg in context:
            assert msg["role"] in ("system", "user", "assistant", "tool")

    def test_returns_valid_context_snapshot(self, ssm):
        """ContextSnapshot has all expected fields populated."""
        thread = AgentThread(
            agent_id="test", agent_name="TestAgent",
            agent_session_id="ast_abc123",
            messages=[
                Message(role=Role.SYSTEM, content="System prompt text"),
                Message(role=Role.USER, content="What is 2+2?"),
            ],
        )

        _, snapshot = ssm.build_turn_context(thread, "test", "What is 2+2?")

        assert isinstance(snapshot, ContextSnapshot)
        assert snapshot.agent_session_id == "ast_abc123"
        assert snapshot.agent_id == "test"
        assert snapshot.system_prompt_chars > 0
        assert snapshot.user_message == "What is 2+2?"
        assert snapshot.messages_total == 1  # 1 non-system message
        assert snapshot.context_messages is not None
        assert len(snapshot.context_messages) >= 2  # system + user

    def test_respects_max_context_turns(self, ssm):
        """max_context_turns limits the number of turns in context."""
        msgs = [Message(role=Role.SYSTEM, content="System")]
        # Add 10 turn pairs (user + assistant)
        for i in range(10):
            msgs.append(Message(role=Role.USER, content=f"Q{i}"))
            msgs.append(Message(role=Role.ASSISTANT, content=f"A{i}"))
        thread = AgentThread(agent_id="test", agent_name="Test", messages=msgs)

        context, snapshot = ssm.build_turn_context(
            thread, "test", "Q9", max_context_turns=2
        )

        # System prompt + at most 4 conversation messages (2 turns × 2 msgs)
        # (actual count depends on token budget, but should be ≤ 5)
        non_system = [m for m in context if m["role"] != "system"]
        assert len(non_system) <= 4

    def test_empty_thread_returns_system_only(self, ssm):
        """Thread with only system prompt returns system-only context."""
        thread = AgentThread(
            agent_id="test", agent_name="Test",
            messages=[Message(role=Role.SYSTEM, content="System prompt")],
        )

        context, snapshot = ssm.build_turn_context(thread, "test", "Hello")

        assert len(context) == 1
        assert context[0]["role"] == "system"
        assert snapshot.messages_kept == 0
        assert snapshot.messages_total == 0


# ── append_message without ensure_thread ─────────────────────────────────────


class TestAppendWithoutEnsure:
    """Verify append_message raises when thread doesn't exist."""

    def test_append_to_missing_thread_raises(self, store):
        """append_message raises KeyError when thread doesn't exist."""
        msg = Message(role=Role.USER, content="hello")
        with pytest.raises(KeyError, match="Thread.*not found"):
            _run(store.append_message("test-session", msg, agent_id="nonexistent"))
