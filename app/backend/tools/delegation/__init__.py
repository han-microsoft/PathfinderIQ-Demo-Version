"""delegate_to_agent — inter-agent delegation with live streaming + persistence.

Module role:
    Enables any agent to delegate a task to another agent. When called:
    1. Persists the task as a user message in the target agent's thread
    2. Builds the target agent via AgentRegistry (per-agent client isolation)
    3. Streams the specialist with stream=True
    4. Broadcasts each event to the session broadcaster (→ specialist's tab)
    5. Accumulates content + tool calls for persistence
    6. Persists the assistant message (with tool calls) to the target thread
    7. Returns the response text as the tool result (→ calling agent)

    Each delegation = one full conversation turn in the specialist's thread.
    On reload, the specialist tab shows the exchange with tool call cards.

Key collaborators:
    - agents.registry.build()              — builds the target agent
    - app.foundation.session_broadcaster   — pushes events to frontend
    - app.services.session_store           — persists the exchange
    - app.services.llm._event_mapping      — maps SDK updates to StreamEvents

Dependents:
    Called by: any agent via SDK function invocation (tool call)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Annotated, Any

from agent_framework import tool, AgentSession, AgentResponseUpdate
from pydantic import Field

from app.foundation.models import (
    Message, MessageStatus, Role, StreamEvent, StreamEventType, ToolCall,
)
from app.observability import traced_tool

logger = logging.getLogger(__name__)


def _get_abort_event(session_id: str) -> asyncio.Event | None:
    """Look up the orchestrator's abort event from the chat router.

    The chat router stores abort events in ``_abort_events`` keyed by
    ``(session_id, agent_id)``.  During delegation the orchestrator is
    the active generation, so we look for ``(session_id, "orchestrator")``.

    Returns:
        The ``asyncio.Event`` if found, else ``None``.
    """
    if not session_id:
        return None
    try:
        from app.foundation.abort_registry import abort_events
        return abort_events.get((session_id, "orchestrator"))
    except ImportError:
        return None


async def _stream_specialist_with_retry(
    agent_id: str,
    task: str,
    session_id: str,
    content_buffer: list[str],
    tool_calls: dict[str, ToolCall],
    usage: dict[str, int],
    abort_event: asyncio.Event | None,
    broadcaster: Any,
    agent_registry: Any,
    t_start: float,
    max_retries: int = 3,
) -> Exception | None:
    """Build and stream the specialist agent with retry logic.

    Runs the specialist's agent.run() stream, mapping SDK updates to
    StreamEvents, broadcasting to the specialist tab, and accumulating
    content + tool calls for persistence.

    Args:
        agent_id: Target specialist agent config key.
        task: The task to send to the specialist.
        session_id: Current session ID for abort and persistence.
        content_buffer: Mutable list to accumulate response tokens.
        tool_calls: Mutable dict to accumulate tool calls by ID.
        usage: Mutable dict for token usage tracking.
        abort_event: Orchestrator's abort event (set by user click).
        broadcaster: Session broadcaster for live streaming events.
        agent_registry: Agent registry for building the specialist.
        t_start: Monotonic start time for duration calculation.
        max_retries: Max retry attempts on transient failures.

    Returns:
        The last exception if all retries failed, or None on success.
        If aborted, returns a string (the JSON result) via early return
        from the caller — this function raises no exceptions on abort.
    """
    from app.services.llm._event_mapping import map_update_to_events

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            specialist = agent_registry.build(agent_id)
            sdk_session = AgentSession()

            async for update in specialist.run(task, stream=True, session=sdk_session):
                if not isinstance(update, AgentResponseUpdate):
                    continue

                # Check abort — exit delegation early when user clicks Abort
                if abort_event and abort_event.is_set():
                    logger.info("delegation.aborted: -> %s, session=%s", agent_id, session_id)
                    if broadcaster:
                        broadcaster.broadcast(agent_id, "error", {"error": "Delegation aborted by user"})
                    response_text = "".join(content_buffer)
                    if session_id and response_text:
                        await _persist_assistant_message(
                            session_id, agent_id,
                            response_text + "\n\n[Aborted by user]",
                            list(tool_calls.values()),
                        )
                    # Signal abort via a sentinel — caller checks content_buffer
                    # and returns the abort JSON result
                    return _AbortSentinel(json.dumps({
                        "agent_id": agent_id,
                        "status": "aborted",
                        "response": response_text or "(aborted before any output)",
                        "duration_ms": round((time.monotonic() - t_start) * 1000),
                    }))

                # Map SDK update to StreamEvent list and process each
                for event in map_update_to_events(update, usage):
                    if broadcaster:
                        broadcaster.broadcast(agent_id, event.event.value, event.data)
                    _accumulate_delegation_event(event, content_buffer, tool_calls)

            # Stream completed — break retry loop
            last_error = None
            break

        except Exception as retry_exc:
            last_error = retry_exc
            from app.foundation.retry import should_retry, log_retry
            retry, sleep_secs = should_retry(retry_exc, attempt, max_retries)
            if retry and attempt < max_retries - 1:
                log_retry(f"delegation->{agent_id}", attempt, max_retries, retry_exc, sleep_secs)
                await asyncio.sleep(sleep_secs)
                content_buffer.clear()
                tool_calls.clear()

    return last_error


class _AbortSentinel(Exception):
    """Sentinel returned by _stream_specialist_with_retry on user abort.

    Not a real exception — used as a typed return value to signal that
    the delegation was aborted and the JSON result is ready.
    """
    def __init__(self, result_json: str):
        self.result_json = result_json


def _accumulate_delegation_event(
    event: StreamEvent,
    content_buffer: list[str],
    tool_calls: dict[str, ToolCall],
) -> None:
    """Accumulate a single delegation stream event into the mutable buffers.

    Pure side-effect function — writes to content_buffer and tool_calls in place.
    """
    if event.event == StreamEventType.TOKEN:
        content_buffer.append(event.data.get("token", ""))
    elif event.event == StreamEventType.TOOL_CALL_START:
        tc_id = event.data.get("id", "")
        tool_calls[tc_id] = ToolCall(id=tc_id, name=event.data.get("name", ""))
    elif event.event == StreamEventType.TOOL_CALL_END:
        tc_id = event.data.get("id", "")
        if tc_id in tool_calls:
            tool_calls[tc_id].arguments = event.data.get("arguments", {})
    elif event.event == StreamEventType.TOOL_RESULT:
        tc_id = event.data.get("id", "")
        if tc_id in tool_calls:
            tool_calls[tc_id].result = event.data.get("result", "")


@tool(approval_mode="never_require")
@traced_tool("delegate_to_agent", backend="delegation")
async def delegate_to_agent(
    agent_id: Annotated[str, Field(
        description=(
            "The agent_id (config key) of the specialist agent to delegate to. "
            "Use the EXACT agent_id from your current scenario instructions. "
            "NOT snake_case (network_investigator is WRONG). "
            "Do not invent agent IDs. The available agents depend on the active scenario."
        ),
    )],
    task: Annotated[str, Field(
        description=(
            "The task description to send to the specialist agent. "
            "Include all relevant context: identifiers, constraints, "
            "and what specific information you need back."
        ),
    )],
    **kwargs: Any,
) -> str:
    """Delegate a task to another agent with live streaming and persistence.

    The specialist's tool calls and reasoning stream live into its tab.
    The full exchange is persisted as a conversation turn in the
    specialist's thread — visible on reload.

    Args:
        agent_id: Config key of the target agent.
        task: The task description to send.

    Returns:
        JSON string with agent_id, status, response, duration_ms.
    """
    from agents import registry as _agent_registry
    from app.foundation.request_context import get_session_id
    from app.foundation.session_broadcaster import get_session_broadcaster
    from app.services.llm._event_mapping import map_update_to_events

    t_start = time.monotonic()
    session_id = get_session_id()

    logger.info(
        "delegation.start: -> %s, task_length=%d, session=%s",
        agent_id, len(task), session_id,
    )

    # Get the session broadcaster for live streaming to the specialist tab
    broadcaster = get_session_broadcaster(session_id) if session_id else None
    if broadcaster:
        logger.info(
            "delegation.broadcaster: session=%s, subscribers=%d",
            session_id, broadcaster.subscriber_count,
        )
    else:
        logger.warning("delegation.no_broadcaster: session_id=%r", session_id)

    try:
        # ── 1. Persist task as user message in the specialist's thread ──
        if session_id:
            await _persist_user_message(session_id, agent_id, task)

        # Resolve the abort event for this session's orchestrator so the
        # delegation loop can exit early when the user clicks Abort.
        # The chat router stores abort events keyed by (session_id, agent_id).
        _abort_event = _get_abort_event(session_id)

        # Signal delegation start to the specialist tab
        if broadcaster:
            broadcaster.broadcast(agent_id, "delegation_start", {
                "task": task[:200],  # Preview for UI
            })

        # ── 2. Build and stream the specialist (with retry) ──
        content_buffer: list[str] = []
        tool_calls: dict[str, ToolCall] = {}
        usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}

        last_error = await _stream_specialist_with_retry(
            agent_id, task, session_id,
            content_buffer, tool_calls, usage,
            _abort_event, broadcaster, _agent_registry, t_start,
        )

        # Handle abort sentinel — user clicked Abort during streaming
        if isinstance(last_error, _AbortSentinel):
            return last_error.result_json

        response_text = "".join(content_buffer)
        elapsed = (time.monotonic() - t_start) * 1000

        # If all retries failed but we have partial content, use it
        if last_error and not response_text:
            raise last_error

        if last_error and response_text:
            logger.warning(
                "delegation.partial: -> %s, using partial content (%d chars) after retries",
                agent_id, len(response_text),
            )

        # ── 3. Persist assistant message (with tool calls) ──
        if session_id:
            await _persist_assistant_message(
                session_id, agent_id, response_text, list(tool_calls.values()),
            )

        # Signal delegation complete to the specialist tab
        if broadcaster:
            broadcaster.broadcast(agent_id, "done", {})

        logger.info(
            "delegation.complete: -> %s, duration=%.1fs, response_length=%d, tool_calls=%d",
            agent_id, elapsed / 1000, len(response_text), len(tool_calls),
        )

        return json.dumps({
            "agent_id": agent_id,
            "status": "complete",
            "response": response_text,
            "duration_ms": round(elapsed),
        })

    except asyncio.CancelledError:
        # Task cancelled by _keepalive_wrap abort cascade.
        # Broadcast cleanup to specialist tab (sync — always safe).
        elapsed = (time.monotonic() - t_start) * 1000
        logger.info(
            "delegation.cancelled: -> %s, session=%s, duration=%.1fs",
            agent_id, session_id, elapsed / 1000,
        )
        if broadcaster:
            broadcaster.broadcast(agent_id, "error", {
                "error": "Delegation aborted by user",
            })
        # Re-raise so the cancellation propagates through the SDK and
        # up to _keepalive_wrap's finally block which catches it.
        raise

    except Exception as exc:
        elapsed = (time.monotonic() - t_start) * 1000
        error_msg = str(exc)
        logger.exception(
            "delegation.error: -> %s, duration=%.1fs, error=%s",
            agent_id, elapsed / 1000, error_msg,
        )

        # Signal error to the specialist tab
        if broadcaster:
            broadcaster.broadcast(agent_id, "error", {"error": error_msg[:500]})

        return json.dumps({
            "agent_id": agent_id,
            "status": "error",
            "error": error_msg[:500],
            "duration_ms": round(elapsed),
        })


async def _persist_user_message(session_id: str, agent_id: str, task: str) -> None:
    """Persist the delegation task as a user message in the specialist's thread.

    Ensures the thread exists (creates if needed), then appends the task
    as a user message. This makes the delegation visible in the specialist's
    tab on reload.
    """
    try:
        from app.services.conversation import SessionStateManager
        from app.services.session_store.memory import InMemorySessionStore

        # Get the session store from app state — lazy import to avoid circular deps
        import app.main
        store = app.main.app.state.store

        session = await store.get(session_id)
        if not session:
            logger.warning("delegation.persist: session %s not found", session_id)
            return

        # Ensure the specialist's thread exists
        ssm = SessionStateManager()
        await ssm.ensure_thread(session, session_id, agent_id, store)

        # Persist the task as a user message. Set agent_name to "orchestrator"
        # (the delegating agent) so the frontend can display a label showing
        # who delegated this task. Thread routing uses the agent_id parameter
        # of append_message, not agent_name on the message itself.
        user_msg = Message(
            role=Role.USER,
            content=task,
            agent_name="orchestrator",
            status=MessageStatus.COMPLETE,
        )
        await store.append_message(session_id, user_msg, agent_id=agent_id)

        logger.debug("delegation.persist: user message saved to %s thread", agent_id)
    except Exception as e:
        logger.warning("delegation.persist_user failed: %s", e)


async def _persist_assistant_message(
    session_id: str,
    agent_id: str,
    content: str,
    tool_calls: list[ToolCall],
) -> None:
    """Persist the specialist's response as an assistant message with tool calls.

    This makes the full exchange (thinking, tool calls, final response)
    visible in the specialist's tab on reload.
    """
    try:
        import app.main
        store = app.main.app.state.store

        assistant_msg = Message(
            role=Role.ASSISTANT,
            content=content,
            status=MessageStatus.COMPLETE,
            agent_name=agent_id,
            tool_calls=tool_calls,
        )
        await store.append_message(session_id, assistant_msg, agent_id=agent_id)

        logger.debug(
            "delegation.persist: assistant message saved to %s thread (%d tool calls)",
            agent_id, len(tool_calls),
        )
    except Exception as e:
        logger.warning("delegation.persist_assistant failed: %s", e)
