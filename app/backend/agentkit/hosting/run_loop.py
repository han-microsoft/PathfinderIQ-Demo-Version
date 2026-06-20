"""Generic agent run-loop driver — stall detection, progress, revival, retry.

Module role:
    SDK-agnostic, domain-blind orchestration primitives for streaming an
    agent run with stall detection, automatic revival, and model
    fallback/retry. Lifted from GridIQ's
    ``hosting/fastapi/runtime/_run_loop.py`` (Inc13b) so the chat-runtime
    orchestration lives in agentkit and a consumer's runtime is a thin
    delegate.

    The driver owns the mechanical shell only — the per-update bookkeeping
    (mapping updates to SSE events, counting tool calls, accumulating text)
    stays the caller's concern, dispatched on the typed ``Run*`` yield
    events. The domain-specific revival *prompt text* is injected via the
    ``build_revival`` callable; this module ships no domain wording.

Layer rule:
    ``agentkit.contracts`` + ``agentkit.resilience`` only. Zero SDK import
    (the agent is duck-typed: it must expose ``run(prompt, stream=True,
    session=...) -> AsyncIterator``, overridable via ``run_fn``). Zero
    consumer/domain import.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType
from agentkit.resilience import is_rate_limit, log_retry, should_retry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunProgress:
    """Progress captured from a partially-complete agent run.

    Stores the user-visible text and last tool name observed before a
    stalled run is revived. This local state is the only durable evidence
    available when the SDK iterator stops yielding updates before DONE.
    """

    partial_text: str = ""
    last_tool_name: str = ""


class AgentRunStalledError(asyncio.TimeoutError):
    """Raised when ``agent.run()`` stops yielding updates before completion."""


class AgentRunAbortedError(Exception):
    """Raised when ``abort_event`` fires while waiting for the next SDK update.

    Translated by every caller of ``iter_updates_with_stall_timeout`` into a
    terminal ``ABORTED`` SSE frame. Bypasses the stall-revival logic so the
    cancellation latency is bounded by the abort-wait race, not by the
    stall timeout.
    """


async def iter_updates_with_stall_timeout(
    updates: AsyncIterator[Any],
    *,
    stall_timeout_s: float,
    abort_event: asyncio.Event | None = None,
) -> AsyncIterator[Any]:
    """Yield updates until completion or raise when the stream stalls.

    Converts a silent SDK iterator stall into a timeout exception that
    the runtime can recover from before the outer chat request dies.
    When ``abort_event`` is provided, the wait race also includes the
    abort signal so cancellation latency is bounded by one event tick
    rather than ``stall_timeout_s`` (which can be 30s+).

    Raises:
        AgentRunStalledError: No update arrived within ``stall_timeout_s``.
        AgentRunAbortedError: ``abort_event`` fired before the next update.
    """
    iterator = updates.__aiter__()
    # Subscribe to the abort signal once per call — re-used across loop
    # iterations so we don't allocate a fresh task on every update.
    abort_waiter: asyncio.Task | None = None
    if abort_event is not None:
        abort_waiter = asyncio.create_task(abort_event.wait())
    try:
        while True:
            # Fast-path check before allocating the next __anext__ task.
            if abort_event is not None and abort_event.is_set():
                raise AgentRunAbortedError("Abort fired before next update")

            next_task = asyncio.create_task(iterator.__anext__())
            wait_set: set[asyncio.Task] = {next_task}
            if abort_waiter is not None:
                wait_set.add(abort_waiter)

            try:
                done, _ = await asyncio.wait(
                    wait_set,
                    timeout=stall_timeout_s,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except BaseException:
                # Outer cancellation (e.g. client disconnect) — clean up
                # the in-flight __anext__ task before re-raising.
                next_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                    await next_task
                raise

            if not done:
                # Stall — neither __anext__ nor abort produced within window.
                next_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await next_task
                raise AgentRunStalledError(
                    f"No Agent Framework updates for {stall_timeout_s:.0f}s."
                )

            if abort_waiter is not None and abort_waiter in done:
                # Abort wins — cancel the in-flight __anext__ task cleanly
                # and signal the caller to emit ABORTED. Swallow the
                # cancellation so it does not surface as a generic error.
                next_task.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration, Exception):
                    await next_task
                raise AgentRunAbortedError("Abort fired during run")

            # __anext__ produced — yield the update or terminate cleanly.
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


def record_run_progress(progress: RunProgress, sse_events: list[StreamEvent]) -> None:
    """Persist partial text and last tool name seen in streamed events.

    Captures the minimum recovery context needed to revive a stalled run
    without losing the user-visible partial answer or the last known
    tool boundary.
    """
    for sse_event in sse_events:
        if sse_event.event == StreamEventType.TOKEN:
            progress.partial_text += sse_event.data.get("token", "")
        elif sse_event.event in (
            StreamEventType.TOOL_CALL_START,
            StreamEventType.TOOL_CALL_END,
            StreamEventType.TOOL_RESULT,
        ):
            progress.last_tool_name = (
                sse_event.data.get("name", "") or progress.last_tool_name
            )


__all__ = [
    "AgentRunAbortedError",
    "AgentRunStalledError",
    "RunProgress",
    "iter_updates_with_stall_timeout",
    "record_run_progress",
    # Unified retry/fallback/revival driver + yield-event types.
    "RunUpdate",
    "RunTrailingFlush",
    "RunRateLimited",
    "RunAborted",
    "RunStalledTerminal",
    "RunErrorTerminal",
    "RunToolBlocked",
    "RunCompleted",
    "run_with_retry_and_revival",
]


# ---------------------------------------------------------------------------
# Unified retry/fallback/revival driver
# ---------------------------------------------------------------------------
#
# The driver below owns the mechanical retry+fallback+revival shell that
# previously appeared three times verbatim inside a consumer runtime's
# ``stream_completion`` (main run, reflection round, completion-check pass).
# Callers supply an ``agent_factory`` (closure over their agent build), a
# ``build_revival`` closure (domain revival wording), and dispatch on typed
# yield events. Per-update bookkeeping stays in the caller where it belongs
# — the helper has no opinion on what the caller does with each update.


@dataclass(frozen=True, slots=True)
class RunUpdate:
    """The agent yielded an SDK update. Caller maps it to SSE events.

    Carries the active per-iteration ``call_buffer`` so the caller can
    pass it into ``map_update_to_events`` and observe partial function-
    call argument chunks. The buffer is owned by the helper across the
    iteration and flushed (drained) on every exit path; the caller must
    not flush it itself.
    """

    update: Any
    call_buffer: Any


@dataclass(frozen=True, slots=True)
class RunTrailingFlush:
    """End-of-iteration drain of any tool-call buffers left open.

    Emitted on every exit path of an inner-while iteration (clean break,
    abort, stall, exception). Caller yields these events into the SSE
    stream (or filters them — reflection drops ``TOKEN`` frames).
    """

    events: list[StreamEvent]


@dataclass(frozen=True, slots=True)
class RunRateLimited:
    """A retryable rate-limit exception fired; helper will sleep + retry.

    Caller emits a ``RATE_LIMITED`` SSE frame so the frontend can show
    the retry hint to the operator.
    """

    retry_after: int
    attempt: int


@dataclass(frozen=True, slots=True)
class RunAborted:
    """``abort_event`` fired during iteration. Helper has stopped.

    Caller yields an ``ABORTED`` SSE frame and terminates the generator.
    """

    last_tool_name: str
    model: str


@dataclass(frozen=True, slots=True)
class RunStalledTerminal:
    """Revivals exhausted on the final model in the queue.

    Caller decides emission: the main + reflection paths fall through to
    ``RunErrorTerminal``; the completion-check path treats this as a
    soft failure.
    """

    last_tool_name: str
    model: str


@dataclass(frozen=True, slots=True)
class RunErrorTerminal:
    """Retries + fallback exhausted on a non-stall exception.

    Caller emits an error event and terminates the generator (main +
    reflection paths) or sets a soft-failure flag and breaks
    (completion-check path).
    """

    exc: Exception
    models_tried: list[str]
    model: str


@dataclass(frozen=True, slots=True)
class RunToolBlocked:
    """``tool_block_predicate`` matched and the SDK requested a tool call.

    Emitted only when the caller supplied ``tool_block_predicate``.
    Caller flags the run as failed and breaks; the helper has already
    cancelled the inner iteration.
    """

    update: Any
    model: str


@dataclass(frozen=True, slots=True)
class RunCompleted:
    """The agent finished one full streaming pass without stalling.

    Carries the SDK session reference so the caller can chain follow-on
    turns (the completion-check pass uses ``completed_session`` from
    the main loop).
    """

    session: Any
    model: str


def _default_run_fn(agent: Any, prompt: str, session: Any) -> AsyncIterator[Any]:
    """Default agent invocation — pass the reused SDK ``session`` kwarg.

    Preserves the historical GridIQ behaviour (session reused across
    revivals so the model sees prior tool-call history). Consumers whose
    agent does not accept a ``session`` kwarg (e.g. the echo quickstart)
    inject an alternative ``run_fn`` that omits it.
    """
    return agent.run(prompt, stream=True, session=session)


async def run_with_retry_and_revival(
    *,
    agent_factory: Callable[[str], Any],
    prompt: str,
    session: Any,
    model_queue: Sequence[str],
    max_retries: int,
    stall_timeout_s: float,
    max_revivals: int,
    abort_event: asyncio.Event | None,
    build_revival: Callable[[str, RunProgress, int], str],
    tool_call_buffer_factory: Callable[[], Any],
    log_phase: str = "agent.run",
    log_extra: dict[str, Any] | None = None,
    tool_block_predicate: Callable[[Any], bool] | None = None,
    run_fn: Callable[[Any, str, Any], AsyncIterator[Any]] | None = None,
) -> AsyncIterator[
    RunUpdate
    | RunTrailingFlush
    | RunRateLimited
    | RunAborted
    | RunStalledTerminal
    | RunErrorTerminal
    | RunToolBlocked
    | RunCompleted
]:
    """Drive one agent through the retry/fallback/revival shell.

    Yields typed events; caller dispatches on type.

    Parameters:
        agent_factory: ``(model) -> agent``.
        prompt: Initial user/assistant prompt for the run.
        session: SDK session reused across revivals so the model can see
            prior tool-call history. May be ``None`` when ``run_fn``
            omits the ``session`` kwarg.
        model_queue: Ordered list of model deployments to try.
        max_retries: Max retry attempts per model on a retryable error.
            Pass ``0`` to skip the outer retry loop entirely.
        stall_timeout_s: Per-update silence window before
            ``AgentRunStalledError`` fires.
        max_revivals: Max automatic revival attempts before giving up
            on the current model.
        abort_event: Set to terminate the run early. ``None`` disables
            the iterator-level abort race.
        build_revival: ``(prompt, progress, revival_attempt) -> str``
            returns the (domain) prompt for the next revival attempt.
        tool_call_buffer_factory: Zero-arg factory for the per-iteration
            tool-call buffer. Owned by the helper and drained on every
            exit path.
        log_phase: Log prefix preserving the per-phase log shape.
        log_extra: Optional extra structured-log fields merged into every
            internal log emission.
        tool_block_predicate: Optional ``(update) -> bool``. When
            ``True``, the helper aborts the iteration with
            ``RunToolBlocked``.
        run_fn: Optional ``(agent, prompt, session) -> AsyncIterator``
            overriding how the agent is invoked. Defaults to passing the
            reused ``session`` kwarg.
    """
    if not model_queue:
        raise ValueError("model_queue must be non-empty")
    extra = dict(log_extra or {})
    invoke = run_fn or _default_run_fn

    _completed_for_outer_break = False
    # Track the in-flight model + last progress so terminal events can
    # report them (the inline code used the loop variable directly).
    last_progress: RunProgress = RunProgress()

    for model_idx, current_model in enumerate(model_queue):
        if _completed_for_outer_break:
            break

        # range(max_retries + 1) matches the inline behaviour (one
        # initial attempt + ``max_retries`` retries).
        for attempt in range(max_retries + 1):
            try:
                agent = agent_factory(current_model)
                active_prompt = prompt
                revival_attempt = 0
                active_session = session

                while True:
                    progress = RunProgress()
                    last_progress = progress
                    call_buffer = tool_call_buffer_factory()
                    tool_blocked_update: Any = None
                    try:
                        try:
                            async for update in iter_updates_with_stall_timeout(
                                invoke(agent, active_prompt, active_session),
                                stall_timeout_s=stall_timeout_s,
                                abort_event=abort_event,
                            ):
                                # Abort check between updates — mirrors
                                # the inline pattern.
                                if abort_event is not None and abort_event.is_set():
                                    yield RunAborted(
                                        last_tool_name=progress.last_tool_name or "unknown",
                                        model=current_model,
                                    )
                                    return

                                # ``tool_block_predicate`` guard for the
                                # completion-check pass: if the model
                                # requested any tool, terminate the
                                # iteration before yielding the update.
                                if tool_block_predicate is not None and tool_block_predicate(update):
                                    tool_blocked_update = update
                                    break

                                yield RunUpdate(update=update, call_buffer=call_buffer)
                        finally:
                            # Drain unfinished tool calls on every exit
                            # path so the SSE contract stays clean.
                            trailing = call_buffer.flush_open_calls()
                            if trailing:
                                yield RunTrailingFlush(events=list(trailing))
                        if tool_blocked_update is not None:
                            yield RunToolBlocked(
                                update=tool_blocked_update,
                                model=current_model,
                            )
                            return
                        # Inner iteration completed cleanly.
                        yield RunCompleted(session=active_session, model=current_model)
                        _completed_for_outer_break = True
                        break
                    except AgentRunAbortedError:
                        logger.info(
                            "%s.aborted",
                            log_phase,
                            extra={
                                **extra,
                                "model": current_model,
                                "last_tool": progress.last_tool_name or "unknown",
                            },
                        )
                        yield RunAborted(
                            last_tool_name=progress.last_tool_name or "unknown",
                            model=current_model,
                        )
                        return
                    except AgentRunStalledError:
                        if revival_attempt >= max_revivals:
                            # Revivals exhausted; propagate to the outer
                            # except so retry/fallback logic can decide
                            # the next step.
                            raise
                        revival_attempt += 1
                        logger.warning(
                            "%s.stalled",
                            log_phase,
                            extra={
                                **extra,
                                "model": current_model,
                                "revival_attempt": revival_attempt,
                                "last_tool": progress.last_tool_name or "unknown",
                                "stall_timeout_s": stall_timeout_s,
                            },
                        )
                        active_prompt = build_revival(
                            prompt, progress, revival_attempt,
                        )
                        # Reuse the same SDK session so the model sees
                        # prior tool-call history. Identical to the
                        # inline behaviour.
                        continue

                if _completed_for_outer_break:
                    break  # exit retry loop on success

            except Exception as exc:  # noqa: BLE001 — catches stall + retryables
                if isinstance(exc, AgentRunStalledError):
                    retry_decision: tuple[bool, float] = (False, 0.0)
                else:
                    retry_decision = should_retry(exc, attempt, max_retries)
                retry, sleep_secs = retry_decision

                if retry:
                    if is_rate_limit(exc):
                        yield RunRateLimited(
                            retry_after=int(sleep_secs),
                            attempt=attempt + 1,
                        )
                    log_retry(
                        log_phase, attempt, max_retries,
                        exc, sleep_secs, model=current_model,
                    )
                    await asyncio.sleep(sleep_secs)
                    continue  # next attempt for this model

                if model_idx < len(model_queue) - 1:
                    # Try next model in the fallback queue.
                    logger.warning(
                        "%s.model_fallback: %s exhausted, falling back to %s",
                        log_phase, current_model, model_queue[model_idx + 1],
                        extra=extra,
                    )
                    break  # break inner-attempts loop → next model

                # Last model + retries exhausted. Differentiate
                # stall-exhaustion from other errors so the caller can
                # log appropriately.
                if isinstance(exc, AgentRunStalledError):
                    yield RunStalledTerminal(
                        last_tool_name=last_progress.last_tool_name or "unknown",
                        model=current_model,
                    )
                else:
                    yield RunErrorTerminal(
                        exc=exc,
                        models_tried=list(model_queue),
                        model=current_model,
                    )
                return

        else:
            # Inner attempt loop ran to exhaustion without ``break``
            # (i.e. all retries used). Continue to the next model.
            continue

    # Outer model loop exited because the run completed (helper already
    # yielded RunCompleted) or model_queue was exhausted by fallback
    # logic that already yielded a terminal sentinel. Nothing more to do.
    return
