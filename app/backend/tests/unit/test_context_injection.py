"""Context injection — orphaned session transcript building.

Tests the behavior currently implemented inline in llm/agent.py L155-227.
These tests lock down the contract BEFORE Phase 4 extracts it into ThreadSyncManager.

The context injection logic:
    1. Detects orphaned sessions (SDK thread has no server-side history)
    2. Filters prior messages (excludes the current user message)
    3. Builds a <prior_conversation> block with role labels and truncation
    4. Prepends the block to the user message
"""

import pytest


# ── Helpers: replicate the inline logic from llm/agent.py L190-223 ───────────


def _build_context_injection(prior_messages: list[dict], user_message: str, messages_dropped: int = 0) -> str:
    """Replicate llm/agent.py's context injection logic for testing.

    Updated to match production code: includes tool arguments, higher
    truncation for tool-bearing messages, and dropped context notification.
    """
    context_lines: list[str] = []

    if messages_dropped > 0:
        context_lines.append(
            f"[Note: {messages_dropped} earlier messages were trimmed from context. "
            f"You are seeing the most recent messages only. "
            f"If you need information from earlier in the conversation, ask the user.]"
        )

    for m in prior_messages:
        role = m.get("role", "unknown").upper()
        content = m.get("content", "")
        tool_calls = m.get("tool_calls", [])
        tool_summary = ""
        if tool_calls:
            tool_details = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    tool_details.append("?")
                    continue
                name = tc.get("function", {}).get("name", tc.get("name", "?"))
                args_raw = tc.get("function", {}).get("arguments", "")
                if isinstance(args_raw, dict):
                    import json as _json
                    args_raw = _json.dumps(args_raw, default=str)
                if isinstance(args_raw, str) and len(args_raw) > 300:
                    args_raw = args_raw[:300] + "..."
                tool_details.append(f"{name}({args_raw})")
            tool_summary = f" [tools: {'; '.join(tool_details)}]"
        if content:
            limit = 4000 if tool_calls else 2000
            truncated = content[:limit] + ("..." if len(content) > limit else "")
            context_lines.append(f"{role}{tool_summary}: {truncated}")
        elif tool_summary:
            context_lines.append(f"{role}{tool_summary}: (tool results only)")

    if not context_lines:
        return user_message

    context_block = "\n".join(context_lines)
    return (
        f"<prior_conversation>\n"
        f"The following is the conversation history from this session. "
        f"Use it as context for the current question.\n\n"
        f"{context_block}\n"
        f"</prior_conversation>\n\n"
        f"{user_message}"
    )


def _filter_prior_messages(messages: list[dict]) -> list[dict]:
    """Replicate llm/agent.py's prior message filtering (L186-191)."""
    prior = [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
    if prior and prior[-1].get("role") == "user":
        prior = prior[:-1]
    return prior


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPriorMessageFiltering:
    """Verify the filter that separates current query from conversation history."""

    def test_removes_last_user_message(self):
        """The current user query is excluded from prior messages."""
        messages = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "current query"},
        ]
        prior = _filter_prior_messages(messages)
        assert len(prior) == 2
        assert prior[-1]["role"] == "assistant"

    def test_single_user_message_returns_empty(self):
        """First message in a session has no prior context."""
        messages = [{"role": "user", "content": "hello"}]
        prior = _filter_prior_messages(messages)
        assert prior == []

    def test_excludes_system_messages(self):
        """System messages are not included in prior context."""
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "current"},
        ]
        prior = _filter_prior_messages(messages)
        assert all(m["role"] != "system" for m in prior)

    def test_empty_messages_returns_empty(self):
        """No messages → no prior context."""
        assert _filter_prior_messages([]) == []


class TestContextInjectionFormat:
    """Verify the <prior_conversation> block format matches llm/agent.py."""

    def test_basic_injection(self):
        """Two-turn history produces correct XML-tagged block."""
        prior = [
            {"role": "user", "content": "What is router R-045?"},
            {"role": "assistant", "content": "Router R-045 is a core router."},
        ]
        result = _build_context_injection(prior, "Is it healthy?")
        assert "<prior_conversation>" in result
        assert "</prior_conversation>" in result
        assert "USER: What is router R-045?" in result
        assert "ASSISTANT: Router R-045 is a core router." in result
        assert result.endswith("Is it healthy?")

    def test_no_prior_messages_returns_original(self):
        """With no history, user message is returned unchanged."""
        result = _build_context_injection([], "hello")
        assert result == "hello"

    def test_tool_calls_include_arguments(self):
        """Assistant messages with tool calls include tool names AND arguments."""
        prior = [
            {"role": "user", "content": "check router"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {"function": {"name": "query_graph", "arguments": '{"query": "g.V()"}'}, "id": "call_1"},
                    {"function": {"name": "query_telemetry", "arguments": '{"query": "Alerts"}'}, "id": "call_2"},
                ],
            },
        ]
        result = _build_context_injection(prior, "and now?")
        assert "[tools:" in result
        assert "query_graph(" in result
        assert "query_telemetry(" in result
        assert "g.V()" in result

    def test_long_content_truncated(self):
        """Messages longer than 2000 chars (no tools) are truncated."""
        long_content = "x" * 3000
        prior = [{"role": "assistant", "content": long_content}]
        result = _build_context_injection(prior, "follow up")
        assert "..." in result
        assert long_content not in result

    def test_tool_bearing_message_higher_truncation(self):
        """Messages WITH tool calls get 4000-char limit (not 2000)."""
        long_content = "x" * 3000
        prior = [{
            "role": "assistant",
            "content": long_content,
            "tool_calls": [{"function": {"name": "query_graph", "arguments": "{}"}, "id": "c1"}],
        }]
        result = _build_context_injection(prior, "follow up")
        # 3000 chars fits within 4000 limit — should NOT be truncated
        assert "..." not in result.split("</prior_conversation>")[0]

    def test_content_exactly_2000_not_truncated(self):
        """Messages exactly 2000 chars are NOT truncated."""
        exact_content = "x" * 2000
        prior = [{"role": "assistant", "content": exact_content}]
        result = _build_context_injection(prior, "follow up")
        assert "..." not in result.split("</prior_conversation>")[0]

    def test_tool_only_message_no_content(self):
        """Tool messages with no content but with tool_calls get summary."""
        prior = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "thinking", "arguments": ""}, "id": "call_1"}],
            },
        ]
        result = _build_context_injection(prior, "next")
        assert "[tools:" in result
        assert "thinking(" in result
        assert "(tool results only)" in result

    def test_role_labels_uppercase(self):
        """Roles appear as uppercase labels (USER, ASSISTANT, TOOL)."""
        prior = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "response"},
        ]
        result = _build_context_injection(prior, "query")
        assert "USER: test" in result
        assert "ASSISTANT: response" in result

    def test_multi_turn_ordering(self):
        """Messages appear in chronological order in the injection block."""
        prior = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "reply2"},
        ]
        result = _build_context_injection(prior, "third")
        # Check ordering by finding positions
        pos_first = result.index("USER: first")
        pos_reply1 = result.index("ASSISTANT: reply1")
        pos_second = result.index("USER: second")
        pos_reply2 = result.index("ASSISTANT: reply2")
        assert pos_first < pos_reply1 < pos_second < pos_reply2


class TestDroppedContextNotification:
    """Verify the agent is notified when messages are dropped from context."""

    def test_dropped_messages_note_present(self):
        """When messages_dropped > 0, a note is prepended."""
        prior = [{"role": "user", "content": "hello"}]
        result = _build_context_injection(prior, "follow up", messages_dropped=5)
        assert "[Note: 5 earlier messages were trimmed" in result

    def test_no_note_when_zero_dropped(self):
        """When messages_dropped=0, no note is injected."""
        prior = [{"role": "user", "content": "hello"}]
        result = _build_context_injection(prior, "follow up", messages_dropped=0)
        assert "[Note:" not in result

    def test_note_appears_before_messages(self):
        """The dropped note appears before the first message."""
        prior = [{"role": "user", "content": "hello"}]
        result = _build_context_injection(prior, "follow up", messages_dropped=3)
        note_pos = result.index("[Note:")
        msg_pos = result.index("USER: hello")
        assert note_pos < msg_pos
