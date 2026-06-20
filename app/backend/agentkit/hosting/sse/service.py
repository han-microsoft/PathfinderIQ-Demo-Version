"""Generic stream-orchestration mechanics for SSE chat surfaces (B1).

Module role:
    Owns the domain-blind mechanics for (a) wrapping a stream generator
    with keepalive heartbeats, abort signalling, and delegation-event
    draining, and (b) projecting each ``StreamEvent`` into a conversation
    turn's lifecycle. The consumer's chat router keeps transport concerns;
    this module keeps stream-state mechanics.

Layer note:
    Imports ``agentkit.contracts`` / ``agentkit.guardrails`` / stdlib only.
    The conversation turn is consumed structurally via
    ``ConversationTurnProtocol`` so agentkit never imports the consumer's
    concrete turn type.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any, Protocol

from agentkit.contracts.models import MessageStatus, StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


class ConversationTurnProtocol(Protocol):
    """Structural contract for the turn ``accumulate_stream_event`` drives.

    The consumer supplies a concrete turn object; agentkit only depends on
    this duck-typed surface so the turn implementation stays consumer-side.
    """

    def accumulate_token(self, token: str) -> None: ...
    def accumulate_tool_call_start(self, call_id: str, name: str) -> None: ...
    def accumulate_tool_call_delta(self, call_id: str, arguments_delta: str) -> None: ...
    def accumulate_tool_call_end(self, call_id: str, arguments: dict) -> None: ...
    def accumulate_tool_result(self, call_id: str, result: Any) -> None: ...
    def merge_metadata(self, metadata: dict[str, Any]) -> None: ...
    async def finalize(self, status: MessageStatus) -> None: ...
    async def finalize_error(self, message: str) -> None: ...
    def get_content(self) -> str: ...


async def wrap_stream_with_keepalive(
    inner: AsyncIterator,
    interval: float,
    *,
    abort_event: asyncio.Event | None = None,
    delegation_queue: asyncio.Queue | None = None,
    session_id: str = "",
    agent_id: str = "",
    request_id: str = "",
) -> AsyncIterator[StreamEvent]:
    """Yield stream events, keepalives, and delegation events from one wrapper.

    The wrapper preserves the long-lived ``__anext__`` task so timeouts do not
    cancel the inner async generator between keepalive heartbeats. The abort
    signal is subscribed once per stream (not per iteration) so a long stream
    does not churn a fresh task per inner event.

    Lifecycle observability:
        Emits ``sse.stream_open``, ``sse.first_token``, and ``sse.stream_close``
        (with ``reason`` ∈ ``{done, error, aborted, stop, exception}``) carrying
        ``session_id``, ``agent_id``, ``request_id``, and ``frame_seq``. The
        identifiers default to empty strings when callers do not provide them;
        ``request_id`` is minted as a UUID4 when empty so each stream is still
        addressable in logs.
    """
    aiter = inner.__aiter__()
    next_task: asyncio.Task | None = None
    abort_waiter: asyncio.Task | None = None
    if abort_event is not None:
        abort_waiter = asyncio.create_task(abort_event.wait())

    # Mint a per-stream correlation id if the caller did not supply one. The
    # value is reused for every lifecycle log so a single stream is greppable.
    if not request_id:
        request_id = uuid.uuid4().hex
    frame_seq = 0
    first_token_logged = False
    close_reason = "stop"  # Updated on natural close / abort / exception.

    _log_extra: dict[str, Any] = {
        "session_id": session_id,
        "agent_id": agent_id,
        "request_id": request_id,
    }
    logger.info("sse.stream_open", extra=dict(_log_extra))

    try:
        while True:
            if abort_event is not None and abort_event.is_set():
                close_reason = "aborted"
                yield StreamEvent(event=StreamEventType.ABORTED)
                return

            if next_task is None:
                next_task = asyncio.ensure_future(aiter.__anext__())

            wait_set: set[asyncio.Task] = {next_task}
            if abort_waiter is not None:
                wait_set.add(abort_waiter)

            done, _ = await asyncio.wait(
                wait_set,
                timeout=interval,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if abort_event is not None and abort_event.is_set():
                close_reason = "aborted"
                yield StreamEvent(event=StreamEventType.ABORTED)
                return

            if next_task in done:
                try:
                    event = next_task.result()
                except StopAsyncIteration:
                    close_reason = "stop"
                    return
                next_task = None
                frame_seq += 1
                # First visible TOKEN frame — record TTFT boundary.
                if (
                    not first_token_logged
                    and event.event == StreamEventType.TOKEN
                    and event.data.get("token")
                ):
                    first_token_logged = True
                    logger.info(
                        "sse.first_token",
                        extra={**_log_extra, "frame_seq": frame_seq},
                    )
                if event.event == StreamEventType.TOOL_CALL_START:
                    logger.info(
                        "sse.tool_call_start",
                        extra={
                            **_log_extra,
                            "frame_seq": frame_seq,
                            "tool_call_id": event.data.get("id", ""),
                            "tool_name": event.data.get("name", ""),
                        },
                    )
                elif event.event == StreamEventType.TOOL_CALL_END:
                    logger.info(
                        "sse.tool_call_end",
                        extra={
                            **_log_extra,
                            "frame_seq": frame_seq,
                            "tool_call_id": event.data.get("id", ""),
                            "tool_name": event.data.get("name", ""),
                        },
                    )
                elif event.event == StreamEventType.DONE:
                    close_reason = "done"
                elif event.event == StreamEventType.ERROR:
                    close_reason = "error"
                elif event.event == StreamEventType.ABORTED:
                    close_reason = "aborted"
                yield event
            else:
                frame_seq += 1
                yield StreamEvent(event=StreamEventType.KEEPALIVE, data={})

            if delegation_queue is not None:
                while True:
                    try:
                        deleg_event = delegation_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    frame_seq += 1
                    yield deleg_event
    except BaseException:
        close_reason = "exception"
        raise
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await next_task
        if abort_waiter is not None and not abort_waiter.done():
            abort_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await abort_waiter
        logger.info(
            "sse.stream_close",
            extra={
                **_log_extra,
                "reason": close_reason,
                "frame_seq": frame_seq,
            },
        )


async def accumulate_stream_event(
    event: StreamEvent,
    turn: ConversationTurnProtocol,
    captured_metadata: dict[str, Any],
    *,
    output_guardrails: list,
    emit_trace: Callable[[str, str], Awaitable[None]],
) -> dict[str, Any] | None:
    """Project one ``StreamEvent`` into a conversation turn lifecycle.

    Returns:
        Updated metadata for non-terminal events, or ``None`` for terminal
        events that should end the stream loop.
    """
    match event.event:
        case StreamEventType.TOKEN:
            turn.accumulate_token(event.data.get("token", ""))

        case StreamEventType.TOOL_CALL_START:
            turn.accumulate_tool_call_start(
                event.data.get("id", ""),
                event.data.get("name", ""),
            )

        case StreamEventType.TOOL_CALL_DELTA:
            # Per-chunk argument fragment — accepted by the lifecycle
            # but not persisted; the ``ToolCallBuffer`` upstream still
            # emits a TOOL_CALL_END once the JSON closes, and that is
            # where the authoritative ``arguments`` dict is set.
            turn.accumulate_tool_call_delta(
                event.data.get("id", ""),
                event.data.get("arguments_delta", ""),
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
            turn.merge_metadata(
                {
                    "model": event.data.get("model", ""),
                    "duration_ms": event.data.get("duration_ms", 0),
                    "prompt_tokens": event.data.get("prompt_tokens", 0),
                    "completion_tokens": event.data.get("completion_tokens", 0),
                    "total_tokens": event.data.get("total_tokens", 0),
                    "estimated_cost_usd": event.data.get("estimated_cost_usd"),
                }
            )

        case StreamEventType.ABORTED:
            await turn.finalize(MessageStatus.ABORTED)
            await emit_trace("aborted", "")
            return None

        case StreamEventType.ERROR:
            message = event.data.get("error", "Unknown error")
            await turn.finalize_error(message)
            await emit_trace("error", message)
            return None

        case StreamEventType.DONE:
            await turn.finalize(MessageStatus.COMPLETE)
            if output_guardrails:
                from agentkit.guardrails._runner import execute_output_guardrails

                await execute_output_guardrails(output_guardrails, turn.get_content())
            await emit_trace("complete", "")
            return None

    return captured_metadata


__all__ = [
    "ConversationTurnProtocol",
    "accumulate_stream_event",
    "wrap_stream_with_keepalive",
]
