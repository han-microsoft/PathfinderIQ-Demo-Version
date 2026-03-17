"""ConversationMetadata — unit tests.

Tests the ``ConversationMetadata`` class from ``app.services.conversation._metadata``.
Covers:
    - generate_title: short, long, empty, whitespace-only, exact boundary
    - compute_summary: empty, user-only, mixed roles, with tool calls, with thinking
"""

import pytest

from app.foundation.models import Message, Role, ToolCall
from app.services.conversation._metadata import ConversationMetadata


class TestGenerateTitle:
    """ConversationMetadata.generate_title()."""

    def test_short_message_no_truncation(self):
        """Messages <=50 chars become the title verbatim."""
        assert ConversationMetadata.generate_title("Hello world") == "Hello world"

    def test_exactly_50_chars_no_ellipsis(self):
        """Message exactly 50 chars does NOT get ellipsis."""
        msg = "a" * 50
        title = ConversationMetadata.generate_title(msg)
        assert title == msg
        assert "\u2026" not in title

    def test_51_chars_gets_ellipsis(self):
        """Message at 51 chars gets truncated + ellipsis."""
        msg = "a" * 51
        title = ConversationMetadata.generate_title(msg)
        assert len(title) == 51  # 50 chars + 1 ellipsis
        assert title.endswith("\u2026")

    def test_long_message_truncated(self):
        """Long messages are cut at 50 chars + ellipsis."""
        msg = "This is a very long message that definitely exceeds the fifty character limit"
        title = ConversationMetadata.generate_title(msg)
        assert len(title) <= 51
        assert title.endswith("\u2026")

    def test_empty_message(self):
        """Empty message produces empty title."""
        assert ConversationMetadata.generate_title("") == ""

    def test_whitespace_only_stripped(self):
        """Whitespace-only message stripped to empty."""
        assert ConversationMetadata.generate_title("   ") == ""

    def test_custom_max_length(self):
        """Custom max_length is respected."""
        title = ConversationMetadata.generate_title("Hello world", max_length=5)
        assert title == "Hello\u2026"


class TestComputeSummary:
    """ConversationMetadata.compute_summary()."""

    def test_empty_messages(self):
        """No messages → all counts zero."""
        result = ConversationMetadata.compute_summary([])
        assert result["message_count"] == 0
        assert result["user_prompt_count"] == 0
        assert result["agent_response_count"] == 0
        assert result["tool_call_count"] == 0
        assert result["thinking_count"] == 0

    def test_user_only(self):
        """Only user messages."""
        msgs = [
            Message(role=Role.USER, content="Q1"),
            Message(role=Role.USER, content="Q2"),
        ]
        result = ConversationMetadata.compute_summary(msgs)
        assert result["message_count"] == 2
        assert result["user_prompt_count"] == 2
        assert result["agent_response_count"] == 0

    def test_mixed_roles(self):
        """Mixed user + assistant messages."""
        msgs = [
            Message(role=Role.USER, content="Q"),
            Message(role=Role.ASSISTANT, content="A"),
            Message(role=Role.USER, content="Q2"),
        ]
        result = ConversationMetadata.compute_summary(msgs)
        assert result["user_prompt_count"] == 2
        assert result["agent_response_count"] == 1
        assert result["message_count"] == 3

    def test_with_tool_calls(self):
        """Tool calls counted across messages."""
        tc1 = ToolCall(name="query_graph", arguments={})
        tc2 = ToolCall(name="search_runbooks", arguments={})
        msgs = [
            Message(role=Role.ASSISTANT, content="Let me check", tool_calls=[tc1, tc2]),
        ]
        result = ConversationMetadata.compute_summary(msgs)
        assert result["tool_call_count"] == 2
        assert result["thinking_count"] == 0

    def test_thinking_calls_counted(self):
        """Thinking tool calls are separately counted."""
        tc_think = ToolCall(name="thinking", arguments={})
        tc_graph = ToolCall(name="query_graph", arguments={})
        msgs = [
            Message(role=Role.ASSISTANT, content="", tool_calls=[tc_think, tc_graph]),
        ]
        result = ConversationMetadata.compute_summary(msgs)
        assert result["tool_call_count"] == 2
        assert result["thinking_count"] == 1
