"""Chat router — SSE streaming, abort, context management.

Module role:
    Handles the core chat interaction flow: receive a user message, stream
    the LLM response as Server-Sent Events (SSE), and persist both messages
    in the session store. Also provides the abort endpoint for cancellation.

Endpoints:
    POST /api/chat/{session_id}       — Send message, stream response via SSE
    POST /api/chat/{session_id}/abort — Cancel an in-flight generation

Streaming protocol (see API_CONTRACT.md):
    The response is ``Content-Type: text/event-stream``. Each frame has:
      ``event: <StreamEventType>\ndata: <JSON>\n\n``
    Terminal events (DONE, ERROR, ABORTED) end the stream.

Key collaborators:
    - ``app.services.llm.LLMService``        – async generator of StreamEvents
    - ``app.services.conversation``          – builds token-budgeted message array
    - ``app.services.session_store``         – persists messages
    - ``sse_starlette.EventSourceResponse``  – ASGI SSE transport

Dependents:
    Called by: frontend ``api/client.ts:streamChat()``
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.deps import get_llm, get_llmops, get_store, get_current_user, get_input_guardrails, get_output_guardrails, User
from app.foundation.errors import ErrorCode, classify_error, generate_error_id, make_error_event
from app.foundation.models import (
    ChatRequest,
    MessageStatus,
    StreamEvent,
    StreamEventType,
)
from app.services.conversation import ConversationTurn, SessionStateManager
from app.services.llm import LLMService
from app.services.session_store import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Active generation abort events — shared registry in foundation layer.
# Imported here for backward compatibility and direct use in this module.
from app.foundation.abort_registry import abort_events as _abort_events

# Maximum time a single chat request can run before being forcibly terminated.
# Covers the full SSE stream lifespan including all tool calls.
# 500s accommodates Fabric cold starts (capacity resume can take 2-3 min)
# plus a full 40-tool-call investigation chain.
import os as _os
CHAT_TIMEOUT_SECONDS = int(_os.getenv("CHAT_TIMEOUT_SECONDS", "300"))

# Keepalive interval for SSE heartbeat events. During long tool executions
# (graph queries, AI Search) the LLM stream emits no events. Without a
# visible heartbeat, the frontend's idle-timeout guard fires after 300s
# and tears down the connection. SSE comment-frame pings (ping=20) keep
# the TCP connection alive through proxies but are invisible to the JS
# event parser and don't reset the frontend timer.
KEEPALIVE_INTERVAL_SECONDS = 15


async def _keepalive_wrap(
    inner: AsyncIterator,
    interval: float,
    abort_event: asyncio.Event | None = None,
) -> AsyncIterator[StreamEvent]:
    """Wrap an async event stream, injecting KEEPALIVE events during silence.

    When the inner stream produces no event for ``interval`` seconds (e.g.
    during a long Fabric Gremlin query or AI Search call), this wrapper
    emits a ``KEEPALIVE`` event. The frontend uses these to reset its
    idle-timeout guard, preventing false "Stream timed out" errors.

    Also monitors ``abort_event``: when the user clicks Abort, the abort
    event is set and this wrapper yields an ABORTED event and returns.
    The ``finally`` block cancels the pending inner-stream task, which
    propagates ``CancelledError`` through the entire chain (including
    delegation tool calls). This is the primary mechanism for terminating
    a stuck generation during delegation.

    Uses a long-lived ``__anext__()`` task that is NOT cancelled on timeout.
    ``asyncio.wait_for()`` would cancel the pending coroutine and corrupt
    the async generator's internal state. Instead, we use ``asyncio.wait()``
    with ``FIRST_COMPLETED`` so the next-event task survives across
    keepalive cycles.

    Args:
        inner: The LLM's ``stream_completion()`` async generator.
        interval: Seconds of silence before emitting a keepalive.
        abort_event: Set by the abort endpoint to cancel the generation.

    Yields:
        StreamEvent — from the inner stream, a KEEPALIVE heartbeat, or
        a terminal ABORTED event when the user cancels.
    """
    aiter = inner.__aiter__()
    # Long-lived task — survives keepalive cycles without cancellation
    next_task: asyncio.Task | None = None
    try:
        while True:
            # ── Immediate abort check ────────────────────────────────
            # Catches abort set during the previous yield (while control
            # was in the consumer processing the last event).
            if abort_event and abort_event.is_set():
                yield StreamEvent(event=StreamEventType.ABORTED)
                return

            # Create or reuse the __anext__() task
            if next_task is None:
                next_task = asyncio.ensure_future(aiter.__anext__())

            # ── Build wait set ───────────────────────────────────────
            # Race: next event vs. abort signal vs. keepalive timeout.
            # If abort_event fires during a long tool call (delegation,
            # Fabric query), we detect it here instead of waiting for
            # the inner stream to yield an update.
            wait_set: set[asyncio.Task] = {next_task}
            abort_waiter: asyncio.Task | None = None
            if abort_event and not abort_event.is_set():
                abort_waiter = asyncio.ensure_future(abort_event.wait())
                wait_set.add(abort_waiter)

            done, _ = await asyncio.wait(
                wait_set,
                timeout=interval,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Clean up the abort waiter (fire-and-forget cancel is safe
            # for Event.wait tasks — no resource leaks).
            if abort_waiter is not None and not abort_waiter.done():
                abort_waiter.cancel()

            # ── Abort wins the race ──────────────────────────────────
            if abort_event and abort_event.is_set():
                yield StreamEvent(event=StreamEventType.ABORTED)
                return

            # ── Inner event wins the race ────────────────────────────
            if next_task in done:
                try:
                    event = next_task.result()
                except StopAsyncIteration:
                    return
                next_task = None
                yield event
            else:
                # Interval elapsed with no event — emit heartbeat.
                # The next_task is still running (not cancelled) and will
                # be checked again on the next loop iteration.
                yield StreamEvent(event=StreamEventType.KEEPALIVE, data={})
    finally:
        # Clean up: cancel the pending inner-stream task.
        # This propagates CancelledError through the entire chain
        # (stream_completion → agent.run → delegate_to_agent →
        # specialist.run), forcefully terminating stuck delegation.
        if next_task is not None and not next_task.done():
            next_task.cancel()
            try:
                await next_task
            except (asyncio.CancelledError, StopAsyncIteration):
                pass


@router.post("/{session_id}")
async def send_message(
    session_id: str,
    req: ChatRequest,
    agent_id: str | None = Query(None, description="Agent ID to use"),
    store: SessionStore = Depends(get_store),
    llm: LLMService = Depends(get_llm),
    user: User = Depends(get_current_user),
    llmops=Depends(get_llmops),
    input_guardrails: list = Depends(get_input_guardrails),
    output_guardrails: list = Depends(get_output_guardrails),
):
    """Send a user message and stream the assistant's response via SSE."""
    # 1. Validate session
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # 1b. Ownership check — delegates to shared helper from sessions router
    from app.routers.sessions import _check_ownership
    _check_ownership(session, user)
    logger.info(
        "auth.chat.authorized",
        extra={"session_id": session_id, "user_oid": user.oid},
    )

    # 2. Per-agent concurrency guard — reject if a generation is already
    #    in flight for this agent in this session.
    _active_agent_id = agent_id or "orchestrator"
    _guard_key = (session_id, _active_agent_id)
    _stale_event = _abort_events.get(_guard_key)
    if _stale_event is not None:
        if _stale_event.is_set():
            # Stale guard key from a previous aborted generation whose
            # finally block hasn't run yet (e.g. delegation was stuck).
            # Clean it up so the user can send a new message.
            _abort_events.pop(_guard_key, None)
            logger.info(
                "chat.stale_guard_cleaned: session=%s, agent=%s",
                session_id, _active_agent_id,
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Generation already in progress for {_active_agent_id}",
            )

    # 3. Ensure the agent's thread exists with the correct system prompt.
    _ssm = SessionStateManager()
    _thread, _is_first = await _ssm.ensure_thread(
        session, session_id, _active_agent_id, store
    )

    # 3a. Create a ConversationTurn to manage the message lifecycle.
    turn = ConversationTurn(session_id, store, agent_id=_active_agent_id)
    await turn.start(session, req.content, is_first_message=_is_first)

    # 3b. Inject session_id into the per-request context so tools can
    #     access it for session-scoped spoof state isolation.
    from app.foundation.request_context import get_request_context, set_request_context, RequestContext
    _ctx = get_request_context()
    set_request_context(RequestContext(
        scenario_name=_ctx.scenario_name,
        llm_model=_ctx.llm_model,
        session_id=session_id,
    ))
    # Also update the frozen RequestScope with session_id
    import dataclasses as _dc
    from app.foundation.request_scope import get_request_scope, set_request_scope
    _scope = get_request_scope()
    set_request_scope(_dc.replace(_scope, session_id=session_id))

    # 4. Set up abort event for this agent
    abort_event = asyncio.Event()
    _abort_events[_guard_key] = abort_event

    async def event_generator():
        """Async generator that yields SSE events.

        Streams LLM responses as SSE frames. Uses ConversationTurn for
        message state accumulation and finalization. The router owns only
        the SSE transport, abort coordination, timeout handling, and
        LLMOps trace emission.
        """
        # Captured from METADATA event for LLMOps tracing (Phase 1.1)
        _captured_metadata: dict = {}
        # Capture scenario from per-request context at generator creation time
        # (not when the trace is emitted later) to prevent mid-conversation bleed
        from app.foundation.request_scope import get_request_scope as _get_scope
        _ctx_scenario = _get_scope().scenario_name or settings.scenario_name

        async def _emit_trace(status: str, error: str = "") -> None:
            """Emit an LLMOps trace if the manager is configured."""
            if not llmops:
                return
            from app.llmops._protocol import LLMTrace
            from app.observability._middleware import request_id_var
            await llmops.trace(LLMTrace(
                trace_id=request_id_var.get(""),
                session_id=session_id,
                model=_captured_metadata.get("model", ""),
                provider=settings.llm_provider,
                prompt_tokens=_captured_metadata.get("prompt_tokens", 0),
                completion_tokens=_captured_metadata.get("completion_tokens", 0),
                total_tokens=_captured_metadata.get("total_tokens", 0),
                duration_ms=_captured_metadata.get("duration_ms", 0.0),
                estimated_cost_usd=_captured_metadata.get("estimated_cost_usd"),
                tool_call_count=len(turn._tool_calls),
                tool_calls=turn.get_tool_names(),
                status=status,
                error=error or None,
                metadata={"user_id": user.oid, "scenario": _ctx_scenario},
            ))

        try:
          async with asyncio.timeout(CHAT_TIMEOUT_SECONDS):
            # Reload session to get the just-appended user message
            current_session = await store.get(session_id)
            if current_session is None:
                yield _format_sse(StreamEvent(
                    event=StreamEventType.ERROR,
                    data={"error": "Session disappeared"},
                ))
                return

            # Build context via SessionStateManager (thread-scoped, isolated).
            _refreshed_thread = current_session.threads.get(_active_agent_id)
            if _refreshed_thread is None:
                _refreshed_thread = _thread
            context, _ctx_snapshot = _ssm.build_turn_context(
                _refreshed_thread,
                _active_agent_id,
                req.content,
                max_context_turns=req.max_context_turns,
            )
            turn.set_context_snapshot(_ctx_snapshot)

            # Input guardrails — check user message before LLM call (Phase 1.6)
            if input_guardrails:
                from app.guardrails._runner import execute_input_guardrails
                block = await execute_input_guardrails(input_guardrails, req.content)
                if block:
                    yield _format_sse(make_error_event(
                        ErrorCode.CONTENT_FILTERED, block.reason,
                    ))
                    return

            # Create placeholder assistant message (status=STREAMING)
            await turn.begin_response()

            # Stream from LLM
            kwargs: dict = {"abort_event": abort_event}
            # Pass session_id for agent-framework session management
            if hasattr(llm, "_get_or_create_session"):
                kwargs["session_id"] = session_id
            # Pass agent_id so the correct agent is built
            kwargs["agent_id"] = _active_agent_id
            # Pass messages_dropped so context injection can notify the agent
            kwargs["messages_dropped"] = _ctx_snapshot.messages_dropped

            async for event in _keepalive_wrap(
                llm.stream_completion(context, **kwargs),
                KEEPALIVE_INTERVAL_SECONDS,
                abort_event=abort_event,
            ):
                # Check for graceful shutdown signal
                from app.foundation._lifecycle import shutdown_event
                if shutdown_event.is_set():
                    yield _format_sse(StreamEvent(event=StreamEventType.ABORTED))
                    return

                # Yield SSE event to client
                yield _format_sse(event)

                # Skip state accumulation for heartbeat events
                if event.event == StreamEventType.KEEPALIVE:
                    continue

                # Delegate state accumulation to extracted helper
                result = await _accumulate_event(
                    event, turn, _captured_metadata,
                    output_guardrails, _emit_trace,
                )
                if result is None:
                    # Terminal event (DONE/ERROR/ABORTED) — stop
                    return
                _captured_metadata = result

        except asyncio.TimeoutError:
            logger.error("Chat timeout after %ds in session %s",
                         CHAT_TIMEOUT_SECONDS, session_id)
            yield _format_sse(make_error_event(
                ErrorCode.TIMEOUT,
                f"Request timed out after {CHAT_TIMEOUT_SECONDS}s.",
            ))

        except Exception as exc:
            # Classify the exception and generate a correlation ID.
            # Raw exception text stays in the server log; only a
            # sanitised message + error_id reach the client.
            error_id = generate_error_id()
            error_code, error_message = classify_error(exc)
            logger.exception(
                "Streaming error in session %s [error_id=%s, code=%s]",
                session_id, error_id, error_code.value,
            )
            yield _format_sse(make_error_event(
                error_code, error_message, error_id=error_id,
            ))
        finally:
            _abort_events.pop(_guard_key, None)
            # If the turn was started but never finalized (client disconnected
            # mid-stream, or an unhandled exception), finalize as ABORTED so
            # the assistant message isn't left as an empty STREAMING placeholder.
            if (turn._assistant_message is not None
                    and turn._assistant_message.status == MessageStatus.STREAMING):
                try:
                    async with asyncio.timeout(5):
                        await turn.finalize(MessageStatus.ABORTED)
                    logger.info(
                        "conversation.turn.auto_finalized",
                        extra={"session_id": session_id, "reason": "client_disconnect"},
                    )
                except Exception:
                    logger.error(
                        "conversation.turn.finalize_failed",
                        extra={"session_id": session_id},
                        exc_info=True,
                    )

    # ping=20 sends a keepalive comment every 20s, preventing proxy/browser
    # idle-timeout disconnects during long tool executions when no SSE events
    # are being emitted by the agent workflow.
    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
        ping=20,
    )


# ── Stream event accumulation ────────────────────────────────────────────────


async def _accumulate_event(
    event: StreamEvent,
    turn: ConversationTurn,
    captured_metadata: dict,
    output_guardrails: list,
    emit_trace,
) -> dict | None:
    """Accumulate a single stream event into the ConversationTurn.

    Handles token/tool_call/metadata/done/error/aborted events. Returns
    the updated captured_metadata dict. Returns None for terminal events
    (DONE, ERROR, ABORTED) to signal the caller to stop iterating.

    Args:
        event: The StreamEvent from the LLM stream.
        turn: The ConversationTurn managing message lifecycle.
        captured_metadata: Mutable dict for LLMOps metadata capture.
        output_guardrails: Output guardrail instances (Phase 1.6).
        emit_trace: Async callable to emit LLMOps trace.

    Returns:
        Updated captured_metadata dict, or None for terminal events.
    """
    match event.event:
        case StreamEventType.TOKEN:
            turn.accumulate_token(event.data.get("token", ""))

        case StreamEventType.TOOL_CALL_START:
            turn.accumulate_tool_call_start(
                event.data.get("id", ""),
                event.data.get("name", ""),
            )

        case StreamEventType.TOOL_CALL_END:
            turn.accumulate_tool_call_end(
                event.data.get("id", ""),
                event.data.get("arguments", {}),
            )

        case StreamEventType.TOOL_RESULT:
            turn.accumulate_tool_result(
                event.data.get("id", ""),
                event.data.get("result", ""),
            )

        case StreamEventType.METADATA:
            captured_metadata.update(event.data)
            # Merge stream metadata into context_snapshot for persistence.
            # This ensures saved conversations retain model, duration, cost.
            turn.merge_metadata({
                "model": event.data.get("model", ""),
                "duration_ms": event.data.get("duration_ms", 0),
                "prompt_tokens": event.data.get("prompt_tokens", 0),
                "completion_tokens": event.data.get("completion_tokens", 0),
                "total_tokens": event.data.get("total_tokens", 0),
                "estimated_cost_usd": event.data.get("estimated_cost_usd"),
            })

        case StreamEventType.ABORTED:
            await turn.finalize(MessageStatus.ABORTED)
            await emit_trace("aborted")
            return None

        case StreamEventType.ERROR:
            await turn.finalize_error(
                event.data.get("error", "Unknown error")
            )
            await emit_trace("error", event.data.get("error", ""))
            return None

        case StreamEventType.DONE:
            await turn.finalize(MessageStatus.COMPLETE)
            # Output guardrails — post-streaming audit (Phase 1.6)
            if output_guardrails:
                from app.guardrails._runner import execute_output_guardrails
                await execute_output_guardrails(
                    output_guardrails, turn.get_content(),
                )
                # WARN/BLOCK logged by runner — advisory only
                # (content already streamed to user)
            await emit_trace("complete")
            return None

    return captured_metadata


# ── Abort ────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/abort", status_code=204)
async def abort_generation(
    session_id: str,
    request: Request,
    agent_id: str | None = Query(None, description="Agent ID to abort"),
    user: User = Depends(get_current_user),
):
    """Cancel an in-flight generation for a session.

    Sets the abort event, which the streaming generator checks on each
    iteration.  The generator will emit an ABORTED event and clean up.
    Also verifies session ownership to prevent cross-user interference.
    """
    # Ownership check — prevents aborting another user's stream
    from app.foundation.config import settings
    if settings.auth_enabled:
        store: SessionStore = request.app.state.store
        session = await store.get(session_id)
        if session and session.user_id not in (user.oid, "__default__", ""):
            logger.warning(
                "auth.abort.denied",
                extra={"session_id": session_id, "user_oid": user.oid},
            )
            raise HTTPException(status_code=404, detail="Session not found")

    # Try the requested agent first, then fall back to "orchestrator".
    # During delegation, only the orchestrator key exists in _abort_events
    # (the specialist runs inside the orchestrator's tool call). Setting
    # the orchestrator's abort event cascades: the orchestrator checks it
    # on each update, and the delegation tool also checks it.
    target_agent = agent_id or "orchestrator"
    event = _abort_events.get((session_id, target_agent))
    if event is None and target_agent != "orchestrator":
        # Specialist has no direct guard key — abort the orchestrator instead
        event = _abort_events.get((session_id, "orchestrator"))
    if event is None:
        # No active generation found — return 204 (idempotent, not an error).
        # This avoids 409 noise when the user clicks abort after the stream
        # already finished or during delegation transitions.
        return
    event.set()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_sse(event: StreamEvent) -> dict:
    """Format a StreamEvent as an SSE-compatible dict for sse-starlette."""
    return {
        "event": event.event.value,
        "data": json.dumps(event.data),
    }
