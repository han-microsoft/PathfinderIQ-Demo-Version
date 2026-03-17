"""Tests for v3 threaded session models: AgentThread, ContextSnapshot, Session, ChatRequest.

Covers:
    - AgentThread auto-generates agent_session_id with "ast_" prefix
    - AgentThread stores messages chronologically
    - ContextSnapshot defaults and optional context_messages
    - Session v3 has threads dict, schema_version=3
    - Session model_validator triggers v2→v3 migration
    - ChatRequest validates content length and max_context_turns
"""

import pytest

from app.foundation.models import (
    AgentThread,
    ChatRequest,
    ContextSnapshot,
    Message,
    Role,
    Session,
)


# ── AgentThread ──────────────────────────────────────────────────────────────


class TestAgentThread:
    """AgentThread construction and defaults."""

    def test_auto_generates_agent_session_id(self):
        """agent_session_id starts with 'ast_' and is 16 chars (ast_ + 12 hex)."""
        thread = AgentThread(agent_id="orchestrator", agent_name="NOCOrchestrator")
        assert thread.agent_session_id.startswith("ast_")
        assert len(thread.agent_session_id) == 16

    def test_unique_ids_across_instances(self):
        """Each AgentThread gets a distinct agent_session_id."""
        t1 = AgentThread()
        t2 = AgentThread()
        assert t1.agent_session_id != t2.agent_session_id

    def test_messages_default_empty(self):
        """Messages list is empty by default."""
        thread = AgentThread(agent_id="net_inv")
        assert thread.messages == []

    def test_stores_messages_in_order(self):
        """Messages appended preserve chronological order."""
        thread = AgentThread(agent_id="orchestrator")
        m1 = Message(role=Role.USER, content="first")
        m2 = Message(role=Role.ASSISTANT, content="second")
        thread.messages.extend([m1, m2])
        assert len(thread.messages) == 2
        assert thread.messages[0].content == "first"
        assert thread.messages[1].content == "second"


# ── ContextSnapshot ──────────────────────────────────────────────────────────


class TestContextSnapshot:
    """ContextSnapshot field defaults and optional context_messages."""

    def test_defaults_all_zeros(self):
        """All numeric fields default to zero, strings to empty."""
        snap = ContextSnapshot()
        assert snap.agent_session_id == ""
        assert snap.agent_id == ""
        assert snap.system_prompt_chars == 0
        assert snap.messages_total == 0
        assert snap.messages_kept == 0
        assert snap.messages_dropped == 0
        assert snap.tokens_used == 0
        assert snap.tokens_budget == 0
        assert snap.max_turns is None
        assert snap.user_message == ""
        assert snap.context_messages is None

    def test_context_messages_optional(self):
        """context_messages can be provided or omitted."""
        snap_with = ContextSnapshot(
            context_messages=[{"role": "system", "content": "hi"}]
        )
        assert len(snap_with.context_messages) == 1

        snap_without = ContextSnapshot()
        assert snap_without.context_messages is None


# ── Session v3 ───────────────────────────────────────────────────────────────


class TestSessionV3:
    """Session v3 schema: threads dict, schema_version=3."""

    def test_default_schema_version_is_3(self):
        """New sessions default to schema_version=3."""
        session = Session()
        assert session.schema_version == 3

    def test_threads_default_empty_dict(self):
        """threads defaults to an empty dict."""
        session = Session()
        assert session.threads == {}
        assert isinstance(session.threads, dict)

    def test_v2_data_auto_migrated(self):
        """Constructing Session from v2 dict (with 'messages' key) triggers migration."""
        v2_data = {
            "id": "sess_v2",
            "title": "Legacy session",
            "schema_version": 2,
            "messages": [
                {"id": "m1", "role": "user", "content": "hello", "agent_name": "orchestrator"},
                {"id": "m2", "role": "assistant", "content": "hi", "agent_name": "orchestrator"},
            ],
        }
        session = Session.model_validate(v2_data)
        assert session.schema_version == 3
        assert "orchestrator" in session.threads
        assert len(session.threads["orchestrator"].messages) == 2


# ── ChatRequest ──────────────────────────────────────────────────────────────


class TestChatRequest:
    """ChatRequest validation: content min/max and max_context_turns."""

    def test_valid_request(self):
        """Normal request passes validation."""
        req = ChatRequest(content="What is the status?")
        assert req.content == "What is the status?"
        assert req.max_context_turns is None

    def test_max_context_turns_accepted(self):
        """max_context_turns is stored when provided."""
        req = ChatRequest(content="query", max_context_turns=5)
        assert req.max_context_turns == 5

    def test_empty_content_rejected(self):
        """Empty string fails min_length=1 validation."""
        with pytest.raises(Exception):
            ChatRequest(content="")
