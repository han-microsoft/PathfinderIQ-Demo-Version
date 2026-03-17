"""Tests for ConversationMetadata.compute_summary_from_threads.

Covers:
    - Empty threads returns all-zero counts
    - Single thread with user+assistant messages counted correctly
    - Multiple threads aggregate counts across all threads
    - System messages excluded from counts
"""

import pytest

from app.foundation.models import AgentThread, Message, Role, ToolCall
from app.services.conversation._metadata import ConversationMetadata


def _make_thread(agent_id: str, messages: list[Message]) -> AgentThread:
    """Helper to build an AgentThread with given messages."""
    return AgentThread(agent_id=agent_id, agent_name=agent_id, messages=messages)


class TestComputeSummaryFromThreads:
    """compute_summary_from_threads: aggregates across v3 threads."""

    def test_empty_threads(self):
        """Empty threads dict returns all-zero counts."""
        result = ConversationMetadata.compute_summary_from_threads({})
        assert result["message_count"] == 0
        assert result["user_prompt_count"] == 0
        assert result["agent_response_count"] == 0
        assert result["tool_call_count"] == 0
        assert result["thinking_count"] == 0

    def test_single_thread_counts(self):
        """Counts user, assistant, and tool calls in a single thread."""
        msgs = [
            Message(role=Role.USER, content="hello"),
            Message(
                role=Role.ASSISTANT,
                content="hi",
                tool_calls=[ToolCall(name="query_graph", arguments={"q": "test"})],
            ),
            Message(role=Role.USER, content="bye"),
            Message(role=Role.ASSISTANT, content="goodbye"),
        ]
        threads = {"orch": _make_thread("orch", msgs)}
        result = ConversationMetadata.compute_summary_from_threads(threads)
        assert result["message_count"] == 4
        assert result["user_prompt_count"] == 2
        assert result["agent_response_count"] == 2
        assert result["tool_call_count"] == 1
        assert result["thinking_count"] == 0

    def test_multiple_threads_aggregate(self):
        """Counts are summed across all threads."""
        t1_msgs = [
            Message(role=Role.USER, content="q1"),
            Message(role=Role.ASSISTANT, content="a1"),
        ]
        t2_msgs = [
            Message(role=Role.USER, content="q2"),
            Message(
                role=Role.ASSISTANT,
                content="a2",
                tool_calls=[
                    ToolCall(name="thinking", arguments={}),
                    ToolCall(name="search_runbooks", arguments={"q": "x"}),
                ],
            ),
        ]
        threads = {
            "orch": _make_thread("orch", t1_msgs),
            "analyzer": _make_thread("analyzer", t2_msgs),
        }
        result = ConversationMetadata.compute_summary_from_threads(threads)
        assert result["message_count"] == 4
        assert result["user_prompt_count"] == 2
        assert result["agent_response_count"] == 2
        assert result["tool_call_count"] == 2
        assert result["thinking_count"] == 1

    def test_system_messages_excluded(self):
        """System messages (message 0) are not counted."""
        msgs = [
            Message(role=Role.SYSTEM, content="You are helpful."),
            Message(role=Role.USER, content="hi"),
            Message(role=Role.ASSISTANT, content="hello"),
        ]
        threads = {"orch": _make_thread("orch", msgs)}
        result = ConversationMetadata.compute_summary_from_threads(threads)
        assert result["message_count"] == 2  # system excluded
        assert result["user_prompt_count"] == 1
        assert result["agent_response_count"] == 1
