"""Conversation lifecycle — message creation, status transitions, tool call assembly.

Tests the behavior currently implemented inline in routers/chat.py event_generator().
These tests lock down the contract BEFORE Phase 3 extracts it into ConversationTurn.

Tested behaviors:
    - Message creation with correct role, content, status defaults
    - MessageStatus transitions: STREAMING → COMPLETE, ERROR, ABORTED
    - ToolCall assembly from streaming events (start → end → result)
    - Message finalization: content buffer join, tool_calls list assembly
"""

import pytest

from app.foundation.models import Message, MessageStatus, Role, ToolCall


# ── Message creation defaults ────────────────────────────────────────────────


class TestMessageCreation:
    """Verify Message model defaults match what routers/chat.py expects."""

    def test_user_message_defaults(self):
        """User messages default to COMPLETE status (no streaming phase)."""
        msg = Message(role=Role.USER, content="Hello")
        assert msg.role == Role.USER
        assert msg.content == "Hello"
        assert msg.status == MessageStatus.COMPLETE
        assert msg.tool_calls == []
        assert msg.id  # UUID generated

    def test_assistant_placeholder_streaming(self):
        """Placeholder assistant message created with STREAMING status."""
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        assert msg.role == Role.ASSISTANT
        assert msg.content == ""
        assert msg.status == MessageStatus.STREAMING

    def test_message_ids_unique(self):
        """Each message gets a unique ID."""
        m1 = Message(role=Role.USER, content="a")
        m2 = Message(role=Role.USER, content="b")
        assert m1.id != m2.id

    def test_message_has_created_at(self):
        """Messages get a UTC timestamp on creation."""
        msg = Message(role=Role.USER, content="test")
        assert msg.created_at is not None


# ── Status transitions ───────────────────────────────────────────────────────


class TestStatusTransitions:
    """Verify that status can be set to all terminal states from STREAMING."""

    def test_streaming_to_complete(self):
        """STREAMING → COMPLETE is the normal success path."""
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.COMPLETE
        msg.content = "Final answer"
        assert msg.status == MessageStatus.COMPLETE
        assert msg.content == "Final answer"

    def test_streaming_to_error(self):
        """STREAMING → ERROR when LLM returns an error."""
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.ERROR
        msg.content = "Something went wrong"
        assert msg.status == MessageStatus.ERROR

    def test_streaming_to_aborted(self):
        """STREAMING → ABORTED when user cancels."""
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.ABORTED
        msg.content = "Partial content"
        assert msg.status == MessageStatus.ABORTED


# ── Tool call assembly ───────────────────────────────────────────────────────


class TestToolCallAssembly:
    """Verify tool call assembly from stream events matches routers/chat.py logic."""

    def test_tool_call_creation(self):
        """ToolCall created with id and name on TOOL_CALL_START."""
        tc = ToolCall(id="call_abc123", name="query_graph")
        assert tc.id == "call_abc123"
        assert tc.name == "query_graph"
        assert tc.arguments == {}
        assert tc.result is None

    def test_tool_call_arguments_set(self):
        """Arguments populated on TOOL_CALL_END."""
        tc = ToolCall(id="call_abc123", name="query_graph")
        tc.arguments = {"query": "MATCH (n) RETURN n LIMIT 5"}
        assert tc.arguments["query"] == "MATCH (n) RETURN n LIMIT 5"

    def test_tool_call_result_set(self):
        """Result populated on TOOL_RESULT."""
        tc = ToolCall(id="call_abc123", name="query_graph")
        tc.result = '{"columns": [], "data": []}'
        assert tc.result is not None

    def test_tool_call_auto_id(self):
        """ToolCall generates an ID if none provided."""
        tc = ToolCall(name="search_runbooks")
        assert tc.id.startswith("call_")

    def test_message_finalization_with_tool_calls(self):
        """Finalized message has content + tool_calls assembled from tracking dicts."""
        # Simulate the accumulation pattern from routers/chat.py
        content_buffer = ["Based on ", "the graph, ", "the router is healthy."]
        tool_calls_dict = {
            "call_1": ToolCall(id="call_1", name="query_graph",
                               arguments={"query": "MATCH (n) RETURN n"},
                               result='{"data": []}'),
            "call_2": ToolCall(id="call_2", name="thinking",
                               arguments={"thoughts": "Analyzing results"},
                               result="ok"),
        }

        # Simulate finalization (routers/chat.py L207-213)
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.COMPLETE
        msg.content = "".join(content_buffer)
        msg.tool_calls = list(tool_calls_dict.values())

        assert msg.content == "Based on the graph, the router is healthy."
        assert len(msg.tool_calls) == 2
        assert msg.tool_calls[0].name == "query_graph"
        assert msg.tool_calls[1].name == "thinking"

    def test_finalization_empty_content(self):
        """Message with no tokens gets empty string content."""
        content_buffer: list[str] = []
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.COMPLETE
        msg.content = "".join(content_buffer)
        assert msg.content == ""

    def test_finalization_aborted_preserves_partial_content(self):
        """Aborted message retains whatever tokens accumulated so far."""
        content_buffer = ["The router ", "is "]  # Aborted mid-sentence
        msg = Message(role=Role.ASSISTANT, content="", status=MessageStatus.STREAMING)
        msg.status = MessageStatus.ABORTED
        msg.content = "".join(content_buffer)
        assert msg.content == "The router is "
        assert msg.status == MessageStatus.ABORTED
