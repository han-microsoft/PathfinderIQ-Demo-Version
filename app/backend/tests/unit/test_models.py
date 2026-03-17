"""Pydantic model validation and serialization."""

from datetime import datetime, timezone

import pytest

from app.foundation.models import (
    ChatRequest,
    Message,
    MessageStatus,
    Role,
    Session,
    SessionSummary,
    StreamEvent,
    StreamEventType,
    StreamMetadata,
    ToolCall,
)


class TestChatRequest:
    def test_rejects_empty(self):
        with pytest.raises(Exception):
            ChatRequest(content="")

    def test_rejects_too_long(self):
        with pytest.raises(Exception):
            ChatRequest(content="x" * 100_001)

    def test_accepts_valid(self):
        req = ChatRequest(content="Hello")
        assert req.content == "Hello"

    def test_accepts_max_length(self):
        req = ChatRequest(content="x" * 100_000)
        assert len(req.content) == 100_000


class TestSession:
    def test_has_auto_id(self):
        s = Session()
        assert s.id
        assert len(s.id) == 32

    def test_default_title(self):
        s = Session()
        assert s.title == "New conversation"

    def test_custom_title(self):
        s = Session(title="My session")
        assert s.title == "My session"

    def test_threads_default_empty(self):
        s = Session()
        assert s.threads == {}

    def test_default_user_id_empty(self):
        """Session.user_id defaults to empty string (anonymous/unscoped)."""
        s = Session()
        assert s.user_id == ""

    def test_user_id_serialization(self):
        """user_id field appears in model_dump output."""
        s = Session(user_id="test-oid-123")
        dumped = s.model_dump()
        assert dumped["user_id"] == "test-oid-123"

    def test_user_id_set_on_construction(self):
        """user_id can be passed at construction time."""
        s = Session(user_id="__default__")
        assert s.user_id == "__default__"


class TestSessionSummaryUserId:
    def test_summary_default_user_id_empty(self):
        """SessionSummary.user_id defaults to empty string."""
        ss = SessionSummary(
            id="x", title="t", message_count=0,
            created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01T00:00:00Z",
        )
        assert ss.user_id == ""

    def test_summary_user_id_set(self):
        """SessionSummary.user_id can be set."""
        ss = SessionSummary(
            id="x", title="t", message_count=0, user_id="abc",
            created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01T00:00:00Z",
        )
        assert ss.user_id == "abc"


class TestMessage:
    def test_default_status_complete(self):
        m = Message(role=Role.USER, content="hi")
        assert m.status == MessageStatus.COMPLETE

    def test_has_auto_id(self):
        m = Message(role=Role.USER, content="hi")
        assert m.id
        assert len(m.id) == 32

    def test_tool_calls_default_empty(self):
        m = Message(role=Role.USER, content="hi")
        assert m.tool_calls == []


class TestToolCall:
    def test_has_auto_id(self):
        tc = ToolCall(name="query_graph")
        assert tc.id.startswith("call_")

    def test_result_default_none(self):
        tc = ToolCall(name="query_graph")
        assert tc.result is None


class TestStreamEvent:
    def test_serializes(self):
        e = StreamEvent(event=StreamEventType.TOKEN, data={"token": "hello"})
        assert e.event == StreamEventType.TOKEN
        assert e.data["token"] == "hello"


class TestStreamMetadata:
    def test_required_fields(self):
        meta = StreamMetadata(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            duration_ms=1234.5,
            model="gpt-4.1",
            assistant_message_id="abc",
        )
        dumped = meta.model_dump()
        assert dumped["prompt_tokens"] == 100
        assert dumped["model"] == "gpt-4.1"


# ── Phase 0 — V2 schema field tests ─────────────────────────────────────────


class TestConversationMetadataWithV2Messages:
    """ConversationMetadata compatibility with v2 messages."""

    def test_compute_summary_with_v2_messages(self):
        """ConversationMetadata.compute_summary works with messages that have
        thread/agent_name fields (doesn't break counting logic)."""
        from app.services.conversation._metadata import ConversationMetadata
        msgs = [
            Message(role=Role.USER, content="hello", thread="orchestrator", agent_name=""),
            Message(role=Role.ASSISTANT, content="hi", thread="orchestrator", agent_name="NOCOrchestrator",
                    tool_calls=[ToolCall(name="query_graph", arguments={})]),
            Message(role=Role.ASSISTANT, content="sub-agent result", thread="hoff_abc", agent_name="NetworkInvestigator"),
        ]
        counts = ConversationMetadata.compute_summary(msgs)
        assert counts["message_count"] == 3
        assert counts["tool_call_count"] == 1
        assert counts["user_prompt_count"] == 1
        assert counts["agent_response_count"] == 2
