"""Generic agent run engine — the full streaming orchestration loop.

Module role:
    The SDK-agnostic, domain-blind heart of a streaming agent turn, lifted
    from GridIQ's ``AgentFrameworkService.stream_completion`` (Inc13b).
    Drives: the main run with retry/fallback/stall-revival, an optional
    reflection loop, a bounded completion-check pass, the empty-completion
    fallback, and the terminal ``METADATA`` + ``DONE`` frames — mapping each
    SDK update to the generic ``StreamEvent`` vocabulary.

    A consumer's runtime becomes a thin delegate: it extracts the user
    message, builds the injected hooks (agent factory, SDK update predicate,
    domain revival wording), and yields from ``run_agent_stream``. Both
    GridIQ's MAF service and ``AgentApp.stream`` run on this one engine.

Injection seams:
    - ``agent_factory(model) -> agent`` — builds/loads the per-model agent.
    - ``session`` + ``run_fn`` — the SDK session reused across revivals and
      how the agent is invoked (the only SDK touch points, supplied by the
      consumer; agentkit imports no SDK here).
    - ``is_update(obj) -> bool`` — filters genuine SDK response updates.
    - ``build_revival`` — domain revival prompt wording (stays consumer-side).
    - ``completion_agent_resolver(model) -> agent | None`` — the agent reused
      for the completion-check pass (``None`` skips the check).

Event-order contract (unchanged): ``token*`` → ``tool_call_*`` / ``tool_result``
interleaved → ``metadata`` → ``done``, or a terminal ``error`` / ``aborted``.

Layer rule:
    ``agentkit.*`` only (contracts, hosting.run_loop, hosting.completion,
    hosting.event_mapping, core.reflection, observability.llmops). Zero SDK
    import; zero consumer/domain import.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType, StreamMetadata
from agentkit.hosting.completion import (
    build_completion_check_prompt,
    build_empty_completion_fallback,
    completion_check_requested_tools,
    is_completion_check_satisfied,
    COMPLETION_CHECK_SENTINEL,
)
from agentkit.hosting.event_mapping import (
    ToolCallBuffer,
    map_update_to_events,
)
from agentkit.hosting.run_loop import (
    AgentRunStalledError,
    RunAborted,
    RunCompleted,
    RunErrorTerminal,
    RunProgress,
    RunRateLimited,
    RunStalledTerminal,
    RunToolBlocked,
    RunTrailingFlush,
    RunUpdate,
    run_with_retry_and_revival,
)

logger = logging.getLogger(__name__)

# The synthetic tool name surfaced for each reflection round. Generic.
REFLECTION_TOOL_NAME = "reflection_assessment"


async def run_agent_stream(
    *,
    prompt: str,
    agent_factory: Callable[[str], Any],
    session: Any,
    is_update: Callable[[Any], bool],
    build_revival: Callable[[str, RunProgress, int], str],
    model_queue: Sequence[str],
    stall_timeout_s: float,
    max_revivals: int,
    max_retries: int = 4,
    abort_event: asyncio.Event | None = None,
    reflection_enabled: bool = False,
    max_reflection_rounds: int = 2,
    completion_agent_resolver: Callable[[str], Any | None] | None = None,
    tool_call_buffer_factory: Callable[[], Any] = ToolCallBuffer,
    run_fn: Callable[[Any, str, Any], AsyncIterator[Any]] | None = None,
    cost_estimator: Callable[[str, int, int], float | None] | None = None,
    fallback_agent_name: str = "agent",
    log_extra: dict[str, Any] | None = None,
) -> AsyncIterator[StreamEvent]:
    """Drive one streaming agent turn and yield generic ``StreamEvent``s.

    The caller has already resolved ``prompt`` (the user message) and the
    injected hooks. This generator owns the run/reflection/completion-check
    orchestration and terminal frames; it never persists or touches HTTP.

    Args:
        prompt: The user message for this turn (non-empty).
        agent_factory: ``(model) -> agent`` building/loading the agent.
        session: SDK session reused across revivals.
        is_update: Predicate selecting genuine SDK response updates.
        build_revival: Domain revival prompt builder.
        model_queue: Ordered model deployments to try (non-empty).
        stall_timeout_s: Per-update silence window before a stall fires.
        max_revivals: Max automatic revival attempts per model.
        max_retries: Max retry attempts per model (main + reflection).
        abort_event: Set to terminate the run early. Raced inside the main
            and reflection iterators; the completion-check pass only checks
            it between updates (preserving the historical latency).
        reflection_enabled: Run the bounded reflection loop when ``True``.
        max_reflection_rounds: Reflection round cap.
        completion_agent_resolver: ``(model) -> agent | None`` for the
            completion-check pass. ``None`` (or a ``None`` return) skips it.
        tool_call_buffer_factory: Per-iteration tool-call buffer factory.
        run_fn: Optional agent-invocation override (see ``run_loop``).
        cost_estimator: ``(model, input_tokens, output_tokens) -> cost`` for
            the metadata frame. ``None`` omits the cost estimate.
        fallback_agent_name: Author name stamped on the empty-completion
            fallback token.
        log_extra: Structured-log context (session_id, agent_id).
    """
    start = time.monotonic()
    assistant_id = uuid.uuid4().hex
    log_extra = dict(log_extra or {})

    tool_call_count = 0
    usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}
    visible_text_emitted = False
    completed_session: Any = session
    current_model = model_queue[0] if model_queue else ""
    agent: Any = None  # captured for the completion-check turn

    logger.info(
        "agent.run.start: model=%s",
        current_model,
        extra=log_extra,
    )

    # ── Phase 1: main run (retry / fallback / stall-revival) ──────────────
    async for evt in run_with_retry_and_revival(
        agent_factory=agent_factory,
        prompt=prompt,
        session=session,
        model_queue=model_queue,
        max_retries=max_retries,
        stall_timeout_s=stall_timeout_s,
        max_revivals=max_revivals,
        abort_event=abort_event,
        build_revival=build_revival,
        tool_call_buffer_factory=tool_call_buffer_factory,
        log_phase="agent.run",
        log_extra=log_extra,
        run_fn=run_fn,
    ):
        if isinstance(evt, RunUpdate):
            update = evt.update
            if not is_update(update):
                continue
            sse_events = map_update_to_events(update, usage, call_buffer=evt.call_buffer)
            for sse_event in sse_events:
                if (
                    sse_event.event == StreamEventType.TOKEN
                    and sse_event.data.get("token", "")
                ):
                    visible_text_emitted = True
                yield sse_event
            tool_call_count += sum(
                1 for c in (getattr(update, "contents", None) or [])
                if getattr(c, "type", "") == "function_call"
            )
        elif isinstance(evt, RunTrailingFlush):
            for trailing in evt.events:
                yield trailing
        elif isinstance(evt, RunRateLimited):
            yield StreamEvent(
                event=StreamEventType.RATE_LIMITED,
                data={"retry_after": evt.retry_after, "attempt": evt.attempt},
            )
        elif isinstance(evt, RunAborted):
            logger.info(
                "agent.run.aborted: model=%s last_tool=%s",
                evt.model, evt.last_tool_name, extra=log_extra,
            )
            yield StreamEvent(event=StreamEventType.ABORTED)
            return
        elif isinstance(evt, RunCompleted):
            completed_session = evt.session
            current_model = evt.model
            if completion_agent_resolver is not None:
                agent = completion_agent_resolver(evt.model)
        elif isinstance(evt, (RunStalledTerminal, RunErrorTerminal)):
            from agentkit.contracts.errors import (
                classify_error, generate_error_id, make_error_event,
            )
            error_id = generate_error_id()
            exc = evt.exc if isinstance(evt, RunErrorTerminal) else AgentRunStalledError(
                f"Stall revivals exhausted on model {evt.model}"
            )
            error_code, error_message = classify_error(exc)
            logger.exception(
                "agent.run.error [error_id=%s, code=%s, models_tried=%s]: %s",
                error_id, error_code.value, list(model_queue), exc, extra=log_extra,
            )
            yield make_error_event(error_code, error_message, error_id=error_id)
            return
        elif isinstance(evt, RunToolBlocked):
            logger.warning(
                "agent.run.tool_blocked_unexpected: model=%s",
                evt.model, extra=log_extra,
            )

    # ── Phase 2: reflection loop (optional) ───────────────────────────────
    if reflection_enabled:
        from agentkit.core.reflection import ReflectionController

        controller = ReflectionController(prompt, max_rounds=max_reflection_rounds)
        logger.info(
            "reflection.start: max_rounds=%d", max_reflection_rounds, extra=log_extra,
        )

        while controller.should_reflect():
            reflection_call_id = f"reflection_{uuid.uuid4().hex[:10]}"
            yield StreamEvent(
                event=StreamEventType.TOOL_CALL_START,
                data={"id": reflection_call_id, "name": REFLECTION_TOOL_NAME},
            )

            assessment_prompt = controller.get_assessment_prompt()
            reflection_response_parts: list[str] = []

            async for evt in run_with_retry_and_revival(
                agent_factory=agent_factory,
                prompt=assessment_prompt,
                session=session,
                model_queue=model_queue,
                max_retries=max_retries,
                stall_timeout_s=stall_timeout_s,
                max_revivals=max_revivals,
                abort_event=abort_event,
                build_revival=build_revival,
                tool_call_buffer_factory=tool_call_buffer_factory,
                log_phase="agent.reflection",
                log_extra=log_extra,
                run_fn=run_fn,
            ):
                if isinstance(evt, RunUpdate):
                    update = evt.update
                    if not is_update(update):
                        continue
                    if getattr(update, "text", ""):
                        reflection_response_parts.append(update.text)
                    sse_events = map_update_to_events(update, usage, call_buffer=evt.call_buffer)
                    for sse_event in sse_events:
                        if sse_event.event == StreamEventType.TOKEN:
                            continue
                        yield sse_event
                    tool_call_count += sum(
                        1 for content in (getattr(update, "contents", None) or [])
                        if getattr(content, "type", "") == "function_call"
                    )
                elif isinstance(evt, RunTrailingFlush):
                    for trailing in evt.events:
                        if trailing.event == StreamEventType.TOKEN:
                            continue
                        yield trailing
                elif isinstance(evt, RunRateLimited):
                    yield StreamEvent(
                        event=StreamEventType.RATE_LIMITED,
                        data={"retry_after": evt.retry_after, "attempt": evt.attempt},
                    )
                elif isinstance(evt, RunAborted):
                    logger.info(
                        "agent.reflection.aborted: model=%s last_tool=%s",
                        evt.model, evt.last_tool_name, extra=log_extra,
                    )
                    yield StreamEvent(event=StreamEventType.ABORTED)
                    return
                elif isinstance(evt, RunCompleted):
                    current_model = evt.model
                elif isinstance(evt, (RunStalledTerminal, RunErrorTerminal)):
                    from agentkit.contracts.errors import (
                        classify_error, generate_error_id, make_error_event,
                    )
                    error_id = generate_error_id()
                    exc = evt.exc if isinstance(evt, RunErrorTerminal) else AgentRunStalledError(
                        f"Stall revivals exhausted on model {evt.model}"
                    )
                    error_code, error_message = classify_error(exc)
                    logger.exception(
                        "agent.reflection.error [error_id=%s, code=%s, models_tried=%s]: %s",
                        error_id, error_code.value, list(model_queue), exc, extra=log_extra,
                    )
                    yield make_error_event(error_code, error_message, error_id=error_id)
                    return

            reflection_text = "".join(reflection_response_parts)
            done = controller.parse_response(reflection_text)
            verdict = "YES" if done else "NO"
            result_payload = {
                "round": controller.round,
                "max_rounds": controller.max_rounds,
                "verdict": verdict,
                "response": reflection_text,
            }
            yield StreamEvent(
                event=StreamEventType.TOOL_CALL_END,
                data={
                    "id": reflection_call_id,
                    "name": REFLECTION_TOOL_NAME,
                    "arguments": {
                        "round": controller.round,
                        "max_rounds": controller.max_rounds,
                        "verdict": verdict,
                    },
                },
            )
            yield StreamEvent(
                event=StreamEventType.TOOL_RESULT,
                data={
                    "id": reflection_call_id,
                    "name": REFLECTION_TOOL_NAME,
                    "result": json.dumps(result_payload),
                },
            )
            if done:
                break

    # ── Phase 3: bounded completion-check pass ────────────────────────────
    continuation_prompt = build_completion_check_prompt(prompt)
    continuation_events: list[StreamEvent] = []
    continuation_text_parts: list[str] = []
    continuation_check_failed = False
    completion_check_requested_tool = False

    def _completion_agent_factory(_model: str) -> Any:
        return agent

    if agent is not None:
        async for evt in run_with_retry_and_revival(
            agent_factory=_completion_agent_factory,
            prompt=continuation_prompt,
            session=completed_session,
            model_queue=[current_model],
            max_retries=0,
            stall_timeout_s=stall_timeout_s,
            max_revivals=max_revivals,
            # The inline code did NOT race abort_event inside the
            # completion-check iterator (only checked between updates).
            abort_event=None,
            build_revival=build_revival,
            tool_call_buffer_factory=tool_call_buffer_factory,
            log_phase="agent.completion_check",
            log_extra=log_extra,
            tool_block_predicate=completion_check_requested_tools,
            run_fn=run_fn,
        ):
            if isinstance(evt, RunUpdate):
                update = evt.update
                # Manual abort check between updates (mirrors the inline
                # code, which had no iterator-level race).
                if abort_event is not None and abort_event.is_set():
                    yield StreamEvent(event=StreamEventType.ABORTED)
                    return
                if not is_update(update):
                    continue
                sse_events = map_update_to_events(update, usage, call_buffer=evt.call_buffer)
                continuation_events.extend(sse_events)
                for sse_event in sse_events:
                    if (
                        sse_event.event == StreamEventType.TOKEN
                        and sse_event.data.get("token", "")
                    ):
                        continuation_text_parts.append(sse_event.data.get("token", ""))
            elif isinstance(evt, RunTrailingFlush):
                continuation_events.extend(evt.events)
            elif isinstance(evt, RunToolBlocked):
                completion_check_requested_tool = True
                continuation_check_failed = True
                logger.warning(
                    "agent.completion_check.blocked_tool: model=%s",
                    evt.model, extra=log_extra,
                )
            elif isinstance(evt, RunStalledTerminal):
                continuation_check_failed = True
                logger.warning(
                    "agent.completion_check.stalled: model=%s last_tool=%s timeout_s=%.1f",
                    evt.model, evt.last_tool_name, stall_timeout_s, extra=log_extra,
                )
            elif isinstance(evt, RunErrorTerminal):
                continuation_check_failed = True
                logger.warning(
                    "agent.completion_check.error: model=%s error=%s",
                    evt.model, evt.exc, extra=log_extra,
                )
            elif isinstance(evt, RunAborted):
                yield StreamEvent(event=StreamEventType.ABORTED)
                return
            # RunCompleted / RunRateLimited: nothing extra to do here.

    continuation_text = "".join(continuation_text_parts)
    if continuation_check_failed:
        logger.warning(
            "agent.completion_check.skipped: reason=%s",
            "tool_request" if completion_check_requested_tool else "error_or_stall",
            extra=log_extra,
        )
    elif is_completion_check_satisfied(continuation_text, continuation_events):
        logger.info("agent.completion_check.complete", extra=log_extra)
    else:
        logger.info(
            "agent.completion_check.continues: buffered_events=%d",
            len(continuation_events), extra=log_extra,
        )
        for continuation_event in continuation_events:
            if (
                continuation_event.event == StreamEventType.TOKEN
                and continuation_event.data.get("token", "").strip() == COMPLETION_CHECK_SENTINEL
            ):
                continue
            if (
                continuation_event.event == StreamEventType.TOKEN
                and continuation_event.data.get("token", "")
            ):
                visible_text_emitted = True
            yield continuation_event

    # ── Empty-completion fallback ─────────────────────────────────────────
    if not visible_text_emitted:
        fallback_text = build_empty_completion_fallback(tool_call_count=tool_call_count)
        logger.warning(
            "agent.run.empty_completion: tool_calls=%d",
            tool_call_count, extra=log_extra,
        )
        yield StreamEvent(
            event=StreamEventType.TOKEN,
            data={"token": fallback_text, "agent": getattr(agent, "name", fallback_agent_name)},
        )

    # ── Phase 4: metadata + DONE ──────────────────────────────────────────
    elapsed = (time.monotonic() - start) * 1000
    request_model = current_model
    logger.info(
        "agent.run.complete: %.1fs total, %d tool calls",
        elapsed / 1000, tool_call_count, extra=log_extra,
    )

    cost = cost_estimator(request_model, usage["input"], usage["output"]) if cost_estimator else None

    yield StreamEvent(
        event=StreamEventType.METADATA,
        data=StreamMetadata(
            prompt_tokens=usage["input"],
            completion_tokens=usage["output"],
            total_tokens=usage["total"],
            duration_ms=elapsed,
            model=request_model,
            assistant_message_id=assistant_id,
            estimated_cost_usd=cost,
        ).model_dump(),
    )
    yield StreamEvent(event=StreamEventType.DONE)


__all__ = ["run_agent_stream", "REFLECTION_TOOL_NAME"]
