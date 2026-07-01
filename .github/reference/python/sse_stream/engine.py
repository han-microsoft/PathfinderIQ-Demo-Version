"""engine — the streaming orchestration spine. Stall, abort, terminal frames.

Reference exemplar. The choreography a naive `async for update in agent.run()`
misses: a hung model must not hang the request (stall timeout), a client cancel
must end the stream cleanly (abort), open tool calls must close before the end,
and the stream must always finish with exactly one terminal frame preceded by
METADATA. Lifted + simplified from a production agentkit (the real one adds
retry, model fallback, revival, reflection, completion-check phases — omitted
here to keep the contract legible; the lifecycle below is faithful).

Transport-agnostic: the agent is duck-typed (must expose
`run(prompt, stream=True) -> async iterator of updates`); nothing here imports a
web framework or an SDK. Stdlib only.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any

from events import StreamEvent, StreamEventType
from mapper import map_update_to_events
from tool_buffer import ToolCallBuffer


class AgentRunStalledError(Exception):
    """No update produced within the stall window — model hung."""


class AgentRunAbortedError(Exception):
    """Abort event fired — client cancelled the stream."""


async def iter_updates_with_stall_timeout(
    iterator: AsyncIterator[Any],
    stall_timeout_s: float,
    abort_event: asyncio.Event | None = None,
) -> AsyncIterator[Any]:
    """Yield updates, racing each against a stall timeout and an abort event.

    Bounds the wait on every `__anext__`: if neither an update nor an abort
    arrives within `stall_timeout_s`, the in-flight task is cancelled and
    AgentRunStalledError is raised. Abort wins immediately when set. No await
    happens between checking and acting, so the abort claim is single-flight.
    """
    abort_waiter = (asyncio.create_task(abort_event.wait())
                    if abort_event is not None else None)
    try:
        while True:
            if abort_event is not None and abort_event.is_set():
                raise AgentRunAbortedError("abort fired before next update")

            next_task = asyncio.create_task(iterator.__anext__())
            wait_set = {next_task}
            if abort_waiter is not None:
                wait_set.add(abort_waiter)

            done, _ = await asyncio.wait(
                wait_set, timeout=stall_timeout_s,
                return_when=asyncio.FIRST_COMPLETED)

            if not done:  # stall — neither update nor abort within window
                next_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_task
                raise AgentRunStalledError(
                    f"no update for {stall_timeout_s:.2f}s")

            if abort_waiter is not None and abort_waiter in done:
                next_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                    await next_task
                raise AgentRunAbortedError("abort fired during run")

            try:
                update = next_task.result()
            except StopAsyncIteration:
                return
            yield update
    finally:
        if abort_waiter is not None and not abort_waiter.done():
            abort_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await abort_waiter


async def run_agent_stream(
    prompt: str,
    agent_factory: Callable[[], Any],
    *,
    run_fn: Callable[[Any, str], AsyncIterator[Any]] | None = None,
    is_update: Callable[[Any], bool] = lambda _u: True,
    stall_timeout_s: float = 30.0,
    abort_event: asyncio.Event | None = None,
    cost_estimator: Callable[[int, int], float | None] | None = None,
) -> AsyncIterator[StreamEvent]:
    """Run an agent and yield the canonical SSE event stream.

    Seams the consumer supplies:
        agent_factory():            build/load the agent instance.
        run_fn(agent, prompt):      how to invoke it (default: agent.run stream).
        is_update(u):               filter SDK metadata-only updates.
        cost_estimator(in, out):    USD estimate for the METADATA frame (optional).
        abort_event:                set to cancel the stream mid-flight.

    Always terminates with exactly one of DONE / ERROR / ABORTED. DONE is
    preceded by METADATA. Open tool calls are flushed before the terminal.
    """
    usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}
    call_buffer = ToolCallBuffer()
    if run_fn is None:
        def run_fn(agent: Any, p: str) -> AsyncIterator[Any]:
            return agent.run(p, stream=True)

    agent = agent_factory()
    iterator = run_fn(agent, prompt).__aiter__()

    try:
        async for update in iter_updates_with_stall_timeout(
                iterator, stall_timeout_s, abort_event):
            if not is_update(update):
                continue
            for ev in map_update_to_events(update, usage, call_buffer=call_buffer):
                yield ev
        # Close any tool call still open at clean end (END before terminal).
        for ev in call_buffer.flush_open_calls():
            yield ev
    except AgentRunAbortedError:
        yield StreamEvent(StreamEventType.ABORTED, {})
        return
    except AgentRunStalledError as exc:
        yield StreamEvent(StreamEventType.ERROR,
                          {"error": "stalled", "detail": str(exc)})
        return
    except Exception as exc:  # noqa: BLE001 — surface any run failure as ERROR
        yield StreamEvent(StreamEventType.ERROR,
                          {"error": "run_failed", "detail": str(exc)})
        return

    meta: dict[str, Any] = {"usage": usage}
    if cost_estimator is not None:
        cost = cost_estimator(usage["input"], usage["output"])
        if cost is not None:
            meta["cost_estimate"] = cost
    yield StreamEvent(StreamEventType.METADATA, meta)
    yield StreamEvent(StreamEventType.DONE, {})


__all__ = ["run_agent_stream", "iter_updates_with_stall_timeout",
           "AgentRunStalledError", "AgentRunAbortedError"]
