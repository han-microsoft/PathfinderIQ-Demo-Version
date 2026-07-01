"""Conversation history context provider (K6) — loads from a session store.

Module role:
    Loads conversation history from the session store and injects it into the
    SDK context as structured messages. Each instance is scoped to one
    (session_id, agent_id) pair. Created per-request. The store is injected via
    constructor — no global state or contextvars; duck-typed (any store exposing
    ``async get(session_id)`` returning an object with ``threads``).

Layering:
    stdlib only (SDK ``Message`` import is lazy inside ``before_run``). No GridIQ
    package. Was ``agent/providers/history.py`` (class ``GridIQHistoryProvider``;
    GridIQ keeps that name as an alias of ``SessionHistoryProvider``).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionHistoryProvider:
    """Loads conversation history from a session store into SDK context.

    Read-only: loads messages in ``before_run()``, does NOT persist in
    ``after_run()`` (the conversation turn handles persistence). Each instance is
    scoped to one (session_id, agent_id) pair. Created per-request.

    Attributes:
        source_id: Provider identifier for message attribution.
    """

    def __init__(self, store: Any, session_id: str, agent_id: str) -> None:
        """Initialize the history provider.

        Args:
            store: Session store instance (InMemory or Cosmos). Injected.
            session_id: Current session ID.
            agent_id: Target agent config key (thread isolation).
        """
        # source_id label kept for back-compat attribution (internal, not wire data).
        self.source_id = "gridiq_history"
        self._store = store
        self._session_id = session_id
        self._agent_id = agent_id

    async def before_run(
        self, *, agent: Any, session: Any, context: Any, state: dict
    ) -> None:
        """Load thread messages from the session store and inject into context.

        Loads all non-system messages from the agent's thread. Removes the last
        user message (that's the current query — sent separately as the
        ``agent.run()`` input). Injects the rest as structured SDK Message
        objects via ``context.extend_messages()``.
        """
        try:
            from agent_framework import Message as SDKMessage
        except ImportError:
            return

        try:
            session_obj = await self._store.get(self._session_id)
            if not session_obj:
                return

            thread = session_obj.threads.get(self._agent_id)
            if not thread:
                return

            sdk_messages = []
            for msg in thread.messages:
                # Skip system messages — SDK handles instructions separately
                if msg.role.value == "system":
                    continue
                # Skip messages with no text content
                if not msg.content or not msg.content.strip():
                    continue
                try:
                    sdk_messages.append(
                        SDKMessage(role=msg.role.value, text=msg.content)
                    )
                except Exception:
                    continue

            # Remove the last user message — it's the current query being sent as
            # the agent.run() input. Including it would duplicate it.
            if sdk_messages and getattr(sdk_messages[-1], "role", "") == "user":
                sdk_messages = sdk_messages[:-1]

            if sdk_messages:
                context.extend_messages(self.source_id, sdk_messages)
                logger.info(
                    "history.loaded",
                    extra={
                        "session_id": self._session_id,
                        "agent_id": self._agent_id,
                        "message_count": len(sdk_messages),
                    },
                )

        except Exception as e:
            # Fail-open: history loading failure must never block the chat
            logger.warning("history.before_run.failed: %s", str(e)[:200])

    async def after_run(
        self, *, agent: Any, session: Any, context: Any, state: dict
    ) -> None:
        """No-op — the conversation turn handles message persistence."""
        pass
