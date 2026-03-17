"""Conversation metadata — title generation, activity summaries, tool names.

Module role:
    Provides reusable functions for deriving conversation-level metadata
    from message content. Replaces inline string slicing (auto-title) and
    inline counting loops (session sidebar activity counts).

    Extracted from ``routers/chat.py`` (title) and ``session_store/memory.py``
    (activity counts) in Phase 5.

Role in system:
    Part of the ``conversation`` service package. Used by ``_lifecycle.py``
    for title generation and by session store implementations for sidebar
    summary computation.

Key collaborators:
    - ``app.models.Message`` — input message objects
    - ``app.services.conversation._lifecycle`` — calls ``generate_title()``
    - ``app.services.session_store.memory`` — calls ``compute_summary()``

Dependents:
    - ``app.services.conversation.__init__`` — re-exports public API
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.foundation.models import Message

logger = logging.getLogger(__name__)


class ConversationMetadata:
    """Tracks conversation-level metadata derived from message content.

    All methods are static — no instance state. This class serves as a
    namespace grouping related metadata functions.
    """

    @staticmethod
    def generate_title(content: str, max_length: int = 50) -> str:
        """Generate a session title from user message content.

        Takes the first ``max_length`` characters of the message content,
        stripping whitespace. If the message exceeds ``max_length``, appends
        a unicode ellipsis character.

        Args:
            content: The user's message text.
            max_length: Maximum title length before truncation (default: 50).

        Returns:
            A title string, at most ``max_length + 1`` characters (including
            the optional ellipsis).

        Side effects:
            Emits structured log ``conversation.metadata.title_generated``.

        Note:
            Upgradeable to LLM-based title generation in future phases.
        """
        title = content[:max_length].strip()
        if len(content) > max_length:
            title += "\u2026"  # Unicode ellipsis

        logger.info(
            "conversation.metadata.title_generated",
            extra={
                "title": title,
                "source_length": len(content),
                "truncated": len(content) > max_length,
            },
        )

        return title

    @staticmethod
    def compute_summary(messages: list[Message]) -> dict:
        """Compute activity counts from messages.

        Scans all messages to produce sidebar display counts:
        user prompts, agent responses, tool calls, and thinking calls.

        Args:
            messages: Full list of messages in a session.

        Returns:
            Dict with keys: ``user_prompt_count``, ``agent_response_count``,
            ``tool_call_count``, ``thinking_count``, ``message_count``.

        Side effects:
            None — pure function.
        """
        tool_call_count = 0
        thinking_count = 0

        for msg in messages:
            for tc in msg.tool_calls:
                tool_call_count += 1
                # The "thinking" tool is a structured reasoning no-op
                if tc.name == "thinking":
                    thinking_count += 1

        return {
            "message_count": len(messages),
            "user_prompt_count": sum(1 for m in messages if m.role == "user"),
            "agent_response_count": sum(
                1 for m in messages if m.role == "assistant"
            ),
            "tool_call_count": tool_call_count,
            "thinking_count": thinking_count,
        }

    @staticmethod
    def compute_summary_from_threads(threads: dict) -> dict:
        """Compute activity counts aggregated across all agent threads.

        Single-pass iteration: counts messages, roles, tool calls, and
        thinking calls in one loop. System messages (message 0) are excluded
        from all counts.

        Args:
            threads: Dict of AgentThread objects keyed by agent_id.

        Returns:
            Dict with keys: ``user_prompt_count``, ``agent_response_count``,
            ``tool_call_count``, ``thinking_count``, ``message_count``.

        Side effects:
            None — pure function.
        """
        message_count = 0
        user_count = 0
        assistant_count = 0
        tool_call_count = 0
        thinking_count = 0

        for thread in threads.values():
            # thread can be AgentThread object or dict (from migration)
            msgs = thread.messages if hasattr(thread, "messages") else thread.get("messages", [])
            for msg in msgs:
                role = msg.role if hasattr(msg, "role") else msg.get("role", "")
                role_str = role.value if hasattr(role, "value") else str(role)
                # Exclude system messages — they're prompts, not conversation
                if role_str == "system":
                    continue
                message_count += 1
                if role_str == "user":
                    user_count += 1
                elif role_str == "assistant":
                    assistant_count += 1
                # Count tool calls on this message
                tcs = msg.tool_calls if hasattr(msg, "tool_calls") else msg.get("tool_calls", [])
                for tc in tcs:
                    tool_call_count += 1
                    tc_name = tc.name if hasattr(tc, "name") else tc.get("name", "")
                    if tc_name == "thinking":
                        thinking_count += 1

        return {
            "message_count": message_count,
            "user_prompt_count": user_count,
            "agent_response_count": assistant_count,
            "tool_call_count": tool_call_count,
            "thinking_count": thinking_count,
        }
