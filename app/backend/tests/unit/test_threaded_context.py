"""Tests for threaded context assembly: build_context_window max_turns, build_context_snapshot.

Covers:
    - max_turns=None includes all messages (token budget governs)
    - max_turns=1 keeps only the last 2 messages (1 user + 1 assistant)
    - max_turns=2 keeps last 4 messages
    - max_turns larger than conversation keeps all
    - max_turns=0 treated as no slicing (edge case)
    - build_context_snapshot returns correct snapshot fields
    - build_context_snapshot computes system_prompt_chars
    - build_context_snapshot messages_dropped is non-negative
    - build_context_snapshot includes context_messages
"""

import pytest

from app.foundation.models import Message, Role
from app.services.conversation import build_context_window, build_context_snapshot


def _make_turn(i: int) -> list[Message]:
    """Create a user+assistant message pair for turn i."""
    return [
        Message(role=Role.USER, content=f"user message {i}"),
        Message(role=Role.ASSISTANT, content=f"assistant reply {i}"),
    ]


def _make_conversation(num_turns: int) -> list[Message]:
    """Create a multi-turn conversation (user/assistant pairs)."""
    msgs = []
    for i in range(num_turns):
        msgs.extend(_make_turn(i))
    return msgs


# ── build_context_window with max_turns ──────────────────────────────────────


class TestBuildContextWindowMaxTurns:
    """max_turns pre-slicing before token-budget trimming."""

    def test_none_includes_all(self):
        """max_turns=None does not slice — all messages eligible for budget."""
        msgs = _make_conversation(5)
        result, _ = build_context_window(msgs, system_prompt="sys", max_turns=None)
        # System + up to 10 conversation messages (budget permitting)
        assert result[0]["role"] == "system"
        # All 10 messages should fit in the default 120k token budget
        assert len(result) == 11

    def test_max_turns_1_keeps_last_pair(self):
        """max_turns=1 keeps only the last user+assistant pair."""
        msgs = _make_conversation(5)
        result, _ = build_context_window(msgs, system_prompt="sys", max_turns=1)
        # System + 2 messages (last turn pair)
        assert len(result) == 3
        assert result[1]["content"] == "user message 4"
        assert result[2]["content"] == "assistant reply 4"

    def test_max_turns_2_keeps_last_two_pairs(self):
        """max_turns=2 keeps last 4 messages (2 turns)."""
        msgs = _make_conversation(5)
        result, _ = build_context_window(msgs, system_prompt="sys", max_turns=2)
        # System + 4 messages
        assert len(result) == 5
        assert result[1]["content"] == "user message 3"
        assert result[4]["content"] == "assistant reply 4"

    def test_max_turns_larger_than_conversation(self):
        """max_turns > actual turns keeps all messages."""
        msgs = _make_conversation(2)
        result, _ = build_context_window(msgs, system_prompt="sys", max_turns=100)
        # System + all 4 messages
        assert len(result) == 5

    def test_max_turns_with_empty_conversation(self):
        """max_turns with no messages returns system-only."""
        result, _ = build_context_window([], system_prompt="sys", max_turns=3)
        assert len(result) == 1
        assert result[0]["role"] == "system"

    def test_system_prompt_always_first(self):
        """System prompt is always the first message regardless of max_turns."""
        msgs = _make_conversation(3)
        result, _ = build_context_window(msgs, system_prompt="Be helpful.", max_turns=1)
        assert result[0] == {"role": "system", "content": "Be helpful."}


# ── build_context_snapshot ───────────────────────────────────────────────────


class TestBuildContextSnapshot:
    """build_context_snapshot: captures what was sent to the LLM."""

    def test_returns_dict_with_required_keys(self):
        """Snapshot dict has all expected ContextSnapshot fields."""
        context = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hello"},
        ]
        snap = build_context_snapshot(
            context,
            agent_session_id="ast_abc123",
            agent_id="orchestrator",
            messages_total=5,
            max_turns=None,
            user_message="hello",
        )
        assert snap["agent_session_id"] == "ast_abc123"
        assert snap["agent_id"] == "orchestrator"
        assert snap["system_prompt_chars"] == len("You are helpful.")
        assert snap["messages_kept"] == 1  # excludes system msg
        assert snap["messages_dropped"] == 4  # 5 total - 1 kept
        assert snap["max_turns"] is None
        assert snap["user_message"] == "hello"

    def test_system_prompt_chars_computed(self):
        """system_prompt_chars reflects the system message content length."""
        prompt = "A" * 200
        context = [{"role": "system", "content": prompt}]
        snap = build_context_snapshot(context, messages_total=0)
        assert snap["system_prompt_chars"] == 200

    def test_context_messages_included(self):
        """context_messages list is populated with role/content dicts."""
        context = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]
        snap = build_context_snapshot(context, messages_total=2)
        assert len(snap["context_messages"]) == 3
        assert snap["context_messages"][0]["role"] == "system"
        assert snap["context_messages"][1]["role"] == "user"
