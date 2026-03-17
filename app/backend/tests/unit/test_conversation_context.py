"""Conversation context assembly — token budgeting correctness.

Tests the extracted ``app.services.conversation._context`` module.
Covers:
    - Tool-call-heavy conversations consume extra tokens
    - System prompt overflow (prompt alone exceeds budget)
    - Single message exceeds remaining budget
    - Empty conversation returns system-only
    - Import from canonical package path works
    - Structured log emitted on every context build
"""

import logging

import pytest

from app.foundation.models import Message, Role, ToolCall


# ── Import path tests ────────────────────────────────────────────────────────


class TestImportPaths:
    """Verify canonical import path works."""

    def test_import_from_conversation_package(self):
        """Canonical import path works."""
        from app.services.conversation import build_context_window, count_tokens

        assert callable(build_context_window)
        assert callable(count_tokens)


# ── Core behavior ───────────────────────────────────────────────────────────


class TestContextWindowCore:
    """Core context-window behavior."""

    def test_system_prompt_always_included(self):
        """System message is never trimmed, even with empty conversation."""
        from app.services.conversation import build_context_window

        result, _ = build_context_window([], system_prompt="You are helpful.")
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."

    def test_newest_messages_kept_oldest_dropped(self):
        """When budget exceeded, oldest messages are dropped first."""
        from app.services.conversation import build_context_window

        msgs = [Message(role=Role.USER, content=f"Message {i}") for i in range(50)]
        result, _ = build_context_window(msgs, system_prompt="System")
        assert result[0]["role"] == "system"
        assert len(result) > 1
        # Newest message should always be present
        assert result[-1]["content"] == "Message 49"

    def test_empty_messages_returns_system_only(self):
        """No user messages → output is just the system prompt."""
        from app.services.conversation import build_context_window

        result, _ = build_context_window([])
        assert len(result) == 1
        assert result[0]["role"] == "system"

    def test_all_messages_fit_within_budget(self):
        """When all messages fit, none are dropped."""
        from app.services.conversation import build_context_window

        msgs = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi!"),
        ]
        result, _ = build_context_window(msgs, system_prompt="Be helpful.")
        # system + 2 messages = 3
        assert len(result) == 3


# ── Edge cases (new in Phase 2) ─────────────────────────────────────────────


class TestContextWindowEdgeCases:
    """Edge cases not covered by the original test_context_manager.py."""

    def test_tool_call_heavy_conversation_consumes_extra_tokens(self):
        """Messages with tool calls use more tokens than plain text."""
        from app.services.conversation import build_context_window, count_tokens

        # Create messages with tool calls — these consume extra tokens
        # for the function name and serialized arguments
        tc = ToolCall(name="query_graph", arguments={"query": "g.V().count()"})
        msgs_with_tools = [
            Message(role=Role.USER, content=f"Query {i}", tool_calls=[tc])
            for i in range(50)
        ]
        msgs_plain = [
            Message(role=Role.USER, content=f"Query {i}")
            for i in range(50)
        ]

        result_tools, _ = build_context_window(msgs_with_tools, system_prompt="S")
        result_plain, _ = build_context_window(msgs_plain, system_prompt="S")

        # Tool-call messages take more budget → fewer messages fit
        assert len(result_tools) <= len(result_plain)

    def test_single_message_exceeds_remaining_budget(self):
        """A single message that exceeds the remaining budget is dropped."""
        from app.services.conversation import build_context_window

        # Create one very long message that should exhaust the budget
        huge_msg = Message(role=Role.USER, content="x " * 50000)
        short_msg = Message(role=Role.USER, content="Hello")

        # Oldest (huge) gets dropped, newest (short) is attempted first
        result, _ = build_context_window(
            [huge_msg, short_msg], system_prompt="S"
        )
        # System + at least the short message
        assert len(result) >= 2
        assert result[-1]["content"] == "Hello"

    def test_only_huge_message_dropped(self):
        """If the only message exceeds the budget, result is system-only."""
        from app.services.conversation import build_context_window

        # 500K "x " repetitions ≈ 500K tokens, well beyond the default
        # budget of ~115K tokens. Must be large enough to exceed budget.
        huge_msg = Message(role=Role.USER, content="x " * 500000)
        result, _ = build_context_window(huge_msg_list := [huge_msg], system_prompt="S")
        # The huge message doesn't fit — only system prompt returned
        assert len(result) == 1
        assert result[0]["role"] == "system"

    def test_chronological_order_preserved(self):
        """Output messages are in chronological order (oldest first)."""
        from app.services.conversation import build_context_window

        msgs = [
            Message(role=Role.USER, content="First"),
            Message(role=Role.ASSISTANT, content="Response"),
            Message(role=Role.USER, content="Second"),
        ]
        result, _ = build_context_window(msgs, system_prompt="S")
        # Skip system message at index 0
        contents = [m["content"] for m in result[1:]]
        assert contents == ["First", "Response", "Second"]


# ── Token counting ──────────────────────────────────────────────────────────


class TestCountTokens:
    """Token counting via tiktoken."""

    def test_returns_positive_int(self):
        """count_tokens returns a positive integer for non-empty text."""
        from app.services.conversation import count_tokens

        n = count_tokens("hello world")
        assert isinstance(n, int)
        assert n > 0

    def test_empty_string_zero_tokens(self):
        """Empty string has zero tokens."""
        from app.services.conversation import count_tokens

        assert count_tokens("") == 0

    def test_longer_text_more_tokens(self):
        """Longer text produces more tokens."""
        from app.services.conversation import count_tokens

        short = count_tokens("hi")
        long = count_tokens("This is a much longer sentence with many words")
        assert long > short


# ── Observability ────────────────────────────────────────────────────────────


class TestContextObservability:
    """Structured logging emitted on every context build."""

    def test_structured_log_emitted(self, caplog):
        """build_context_window emits a 'conversation.context_built' log."""
        from app.services.conversation import build_context_window

        with caplog.at_level(logging.INFO, logger="app.services.conversation._context"):
            build_context_window(
                [Message(role=Role.USER, content="test")],
                system_prompt="S",
            )

        # Find the structured log record
        context_logs = [
            r for r in caplog.records if r.message == "conversation.context_built"
        ]
        assert len(context_logs) == 1, f"Expected 1 log, got {len(context_logs)}: {[r.message for r in caplog.records]}"

        record = context_logs[0]
        # Verify structured fields are present
        assert hasattr(record, "messages_total")
        assert hasattr(record, "messages_kept")
        assert hasattr(record, "messages_dropped")
        assert hasattr(record, "tokens_used")
        assert hasattr(record, "tokens_budget")

    def test_log_counts_correct(self, caplog):
        """Log fields accurately reflect the trimming result."""
        from app.services.conversation import build_context_window

        msgs = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi!"),
        ]

        with caplog.at_level(logging.INFO, logger="app.services.conversation._context"):
            result, _ = build_context_window(msgs, system_prompt="Be helpful.")

        context_logs = [
            r for r in caplog.records if r.message == "conversation.context_built"
        ]
        assert len(context_logs) == 1

        record = context_logs[0]
        # Both messages should fit — 0 dropped
        assert record.messages_total == 2
        assert record.messages_kept == 2
        assert record.messages_dropped == 0
        assert record.tokens_used > 0
        assert record.tokens_budget > 0
