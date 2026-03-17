"""Conversation turn lifecycle — message assembly and finalization.

Module role:
    Owns the user→assistant exchange lifecycle for a single chat turn.
    Manages user message creation, auto-titling, placeholder assistant
    message creation, streaming token/tool-call accumulation, and
    finalization (COMPLETE/ERROR/ABORTED) with store persistence.

    Extracted from ``routers/chat.py`` (Phase 3) to separate transport
    (SSE formatting, abort events) from conversation state management.

Role in system:
    Part of the ``conversation`` service package. Called by ``routers/chat.py``
    during the SSE event_generator loop.

Key collaborators:
    - ``app.services.session_store.SessionStore`` — persists messages
    - ``app.models.Message``, ``ToolCall``, ``MessageStatus`` — data models
    - ``app.services.conversation._metadata`` — title generation (Phase 5,
      currently inline)

Dependents:
    - ``app.routers.chat`` — primary consumer
    - ``app.services.conversation.__init__`` — re-exports public API
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.foundation.models import ContextSnapshot, Message, MessageStatus, Role, Session, ToolCall

if TYPE_CHECKING:
    from app.services.session_store import SessionStore

logger = logging.getLogger(__name__)


async def _store_with_retry(
    coro_factory, label: str, *, max_retries: int = 2
) -> None:
    """Retry a session store write operation.

    On transient failures (network, timeout, 5xx), retries up to
    ``max_retries`` times with linear backoff. Logs warnings on
    retry and errors on final failure. Does NOT raise — the chat
    stream continues even if the store write is lost.

    Args:
        coro_factory: Zero-arg callable returning an awaitable.
        label: Human-readable label for log messages.
        max_retries: Maximum retry attempts after the first failure.

    Side effects:
        Logs warnings on transient failures, errors on exhaustion.

    Dependencies:
        None — pure retry logic.
    """
    for attempt in range(max_retries + 1):
        try:
            await coro_factory()
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    "Session write '%s' failed (attempt %d/%d): %s",
                    label, attempt + 1, max_retries + 1, e,
                )
                await asyncio.sleep(1.0)
            else:
                logger.error(
                    "Session write '%s' failed after %d attempts: %s",
                    label, max_retries + 1, e,
                )


class ConversationTurn:
    """Owns the message lifecycle for a single user→assistant exchange.

    Usage pattern (from routers/chat.py):
        turn = ConversationTurn(session_id, store)
        user_msg = await turn.start(session, user_content)
        await turn.begin_response()
        # ... stream events ...
        turn.accumulate_token(token)
        turn.accumulate_tool_call_start(id, name)
        turn.accumulate_tool_call_end(id, arguments)
        turn.accumulate_tool_result(id, result)
        final_msg = await turn.finalize(MessageStatus.COMPLETE)

    Lifecycle:
        ``start()`` → ``begin_response()`` → accumulate_*() → ``finalize()``

    Key collaborators:
        - ``SessionStore`` — message persistence
        - ``routers/chat.py`` — SSE transport layer (calls this class)

    Dependents:
        Called by: ``routers/chat.py`` event_generator
    """

    def __init__(self, session_id: str, store: SessionStore, agent_id: str = "") -> None:
        """Initialize a conversation turn.

        Args:
            session_id: The session this turn belongs to.
            store: SessionStore instance for persistence.
            agent_id: Agent config key that owns this turn (for thread routing).
        """
        self._session_id = session_id
        self._store = store
        self._agent_id = agent_id
        # Accumulation state — populated during streaming
        self._content_buffer: list[str] = []
        self._tool_calls: dict[str, ToolCall] = {}
        self._tool_start_times: dict[str, float] = {}  # tool_id → time.monotonic()
        self._assistant_message: Message | None = None
        # Context snapshot — set by the router after SSM builds context
        self._context_snapshot: ContextSnapshot | None = None
        # Timing for observability
        self._start_time: float = 0.0

    def set_context_snapshot(self, snapshot: ContextSnapshot) -> None:
        """Store the context snapshot to be persisted on the assistant message.

        Called by the chat router after SessionStateManager.build_turn_context()
        produces the snapshot. The snapshot is attached to the assistant message
        during finalize() so the ContextInspector can display it.

        Args:
            snapshot: The ContextSnapshot from build_turn_context().
        """
        self._context_snapshot = snapshot

    def merge_metadata(self, metadata: dict) -> None:
        """Merge stream metadata (model, duration, tokens, cost) into the context snapshot.

        Called by the chat router when the METADATA SSE event arrives.
        Enriches the persisted snapshot so saved conversations retain
        model name, duration, token counts, and cost on reload.

        Args:
            metadata: Dict with keys like model, duration_ms, prompt_tokens, etc.
        """
        if self._context_snapshot is not None:
            for key, value in metadata.items():
                if value is not None:
                    setattr(self._context_snapshot, key, value)

    async def start(self, session: Session, user_content: str, is_first_message: bool = False) -> Message:
        """Create and persist the user message. Auto-title if first message.

        Args:
            session: The current session object. Used to check message count
                     and potentially update the title.
            user_content: The user's message text.
            is_first_message: Whether this is the first conversational message
                in the agent's thread. Provided by SessionStateManager.ensure_thread().
                When True, auto-generates a session title.

        Returns:
            The created user Message.

        Side effects:
            - Persists user message via store.append_message()
            - Updates session title if this is the first message
            - Emits structured log ``conversation.turn.started``
        """
        self._start_time = time.monotonic()

        # Create and persist user message in the agent's thread
        user_message = Message(role=Role.USER, content=user_content, agent_name=self._agent_id)
        await _store_with_retry(
            lambda: self._store.append_message(self._session_id, user_message, agent_id=self._agent_id),
            f"append_user(session={self._session_id})",
        )

        # Auto-title: if this is the first user message, generate a title
        if is_first_message:
            from app.services.conversation._metadata import ConversationMetadata
            session.title = ConversationMetadata.generate_title(user_content)
            await self._store.update(session)

        logger.info(
            "conversation.turn.started",
            extra={
                "session_id": self._session_id,
                "user_message_length": len(user_content),
                "is_first_message": is_first_message,
            },
        )

        return user_message

    async def begin_response(self) -> Message:
        """Create and persist a placeholder assistant message (status=STREAMING).

        Returns:
            The placeholder Message (for ID tracking during streaming).

        Side effects:
            Persists the placeholder via store.append_message().
        """
        self._assistant_message = Message(
            role=Role.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            agent_name=self._agent_id,
        )
        await _store_with_retry(
            lambda: self._store.append_message(
                self._session_id, self._assistant_message, agent_id=self._agent_id
            ),
            f"append_assistant(session={self._session_id})",
        )
        return self._assistant_message

    def accumulate_token(self, token: str) -> None:
        """Append a text token to the content buffer.

        Args:
            token: A single token string from the LLM stream.
        """
        self._content_buffer.append(token)

    def accumulate_tool_call_start(self, tc_id: str, name: str) -> None:
        """Register a new tool call and start its duration timer.

        Args:
            tc_id: The tool call ID from the LLM.
            name: The function name of the tool.
        """
        self._tool_calls[tc_id] = ToolCall(id=tc_id, name=name)
        self._tool_start_times[tc_id] = time.monotonic()

    def accumulate_tool_call_end(self, tc_id: str, arguments: dict) -> None:
        """Finalize a tool call's arguments.

        Args:
            tc_id: The tool call ID.
            arguments: Parsed argument dict for the tool call.
        """
        if tc_id in self._tool_calls:
            self._tool_calls[tc_id].arguments = arguments

    def accumulate_tool_result(self, tc_id: str, result: str) -> None:
        """Record a tool call's result and compute duration.

        Args:
            tc_id: The tool call ID.
            result: The result string returned by the tool.
        """
        if tc_id in self._tool_calls:
            self._tool_calls[tc_id].result = result
            start = self._tool_start_times.get(tc_id)
            if start is not None:
                self._tool_calls[tc_id].duration_ms = round((time.monotonic() - start) * 1000, 1)

    def get_tool_names(self) -> list[str]:
        """Return names of all accumulated tool calls.

        Used by LLMOps tracing (Phase 1.1) to record which tools were
        invoked during this turn without exposing private state.

        Returns:
            List of tool function names in invocation order.
        """
        return [tc.name for tc in self._tool_calls.values()]

    def get_content(self) -> str:
        """Return the accumulated response content text.

        Used by output guardrails (Phase 1.6) to check the full response
        after streaming completes.

        Returns:
            Concatenated content string from all accumulated tokens.
        """
        return "".join(self._content_buffer)

    async def finalize(self, status: MessageStatus) -> Message:
        """Finalize the assistant message — set content, tool_calls, status.

        Assembles the accumulated content buffer and tool calls into the
        assistant message, then persists via store.update_message().

        Args:
            status: Final status (COMPLETE, ERROR, or ABORTED).

        Returns:
            The finalized Message.

        Side effects:
            - Persists finalized message via store.update_message()
            - Emits structured log ``conversation.turn.completed``
        """
        if self._assistant_message is None:
            # Defensive: if finalize called without begin_response
            logger.warning(
                "conversation.turn.finalize called without begin_response",
                extra={"session_id": self._session_id, "status": status.value},
            )
            return Message(role=Role.ASSISTANT, content="", status=status)

        self._assistant_message.status = status
        self._assistant_message.content = "" .join(self._content_buffer)
        self._assistant_message.tool_calls = list(self._tool_calls.values())
        # Attach context snapshot for auditability (set by router via set_context_snapshot)
        if self._context_snapshot is not None:
            self._assistant_message.context_snapshot = self._context_snapshot

        await _store_with_retry(
            lambda: self._store.update_message(
                self._session_id, self._assistant_message, agent_id=self._agent_id
            ),
            f"update_{status.value}(session={self._session_id})",
        )

        # Compute turn duration for observability
        duration_ms = (time.monotonic() - self._start_time) * 1000 if self._start_time else 0
        duration_s = duration_ms / 1000

        # Record OTel metrics for conversation turn completion
        from app.services.conversation._tracing import record_turn_complete
        record_turn_complete(
            status=status.value,
            duration_seconds=duration_s,
            tool_call_count=len(self._tool_calls),
        )

        logger.info(
            "conversation.turn.completed",
            extra={
                "session_id": self._session_id,
                "status": status.value,
                "content_length": len(self._assistant_message.content),
                "tool_call_count": len(self._tool_calls),
                "duration_ms": round(duration_ms),
            },
        )

        # Cleanup per-turn tracking dicts
        self._tool_start_times.clear()
        self._tool_calls.clear()
        self._content_buffer.clear()

        return self._assistant_message

    async def finalize_error(self, error_text: str) -> Message:
        """Convenience: finalize with ERROR status and set error as content.

        Args:
            error_text: The error message to set as content.

        Returns:
            The finalized error Message.
        """
        if self._assistant_message is not None:
            self._assistant_message.content = error_text
            # Clear content buffer so finalize doesn't overwrite
            self._content_buffer.clear()
            self._content_buffer.append(error_text)
        return await self.finalize(MessageStatus.ERROR)
