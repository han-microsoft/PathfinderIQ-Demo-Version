"""Agent event mapping — SDK AgentResponseUpdate → SSE StreamEvent.

Module role:
    Domain-blind mapper (S1) — converts SDK streaming update objects into
    the generic SSE ``StreamEvent`` protocol. Owns ``ToolCallBuffer`` which
    aggregates per-chunk ``function_call`` deltas into a coherent stream of
    TOOL_CALL_START → TOOL_CALL_DELTA* → TOOL_CALL_END events. Also extracts
    token usage data from SDK usage content objects. The SDK update objects
    are accessed by duck-typing (``getattr`` / attribute reads) so this
    module does NOT import the SDK and stays SDK-agnostic.

Key collaborators:
    - Any SDK streaming update with ``author_name`` / ``text`` / ``contents``
      (e.g. ``agent_framework.AgentResponseUpdate``) — read by attribute.
    - Content (type='function_call') — per-chunk fragments whose
      ``arguments`` field is a partial string until the call closes.
    - agentkit.contracts.models.StreamEvent, StreamEventType — SSE protocol.

Dependents:
    A host's streaming runtime (orchestrator / summary / specialist loops)
    feeds updates in and forwards the returned StreamEvents to its SSE
    transport. GridIQ re-exports this module at
    ``hosting.fastapi.streaming.event_mapping`` for back-compat.

Design notes:
    The OpenAI Chat Completions API streams ``tool_calls[i].function.
    arguments`` as growing string fragments. Only the first chunk per call
    carries `call_id` and `name`; subsequent chunks of the SAME call have
    empty `call_id` and append to the most recently-opened call's arg
    buffer. ToolCallBuffer mirrors that grouping so we can emit a single
    coherent lifecycle (START / DELTA* / END) per logical call, even
    across chunks.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from agentkit.contracts.models import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


# ── ToolCallBuffer ──────────────────────────────────────────────────────────


@dataclass
class _ActiveCall:
    """One in-flight tool call.

    Fields:
        id:           Stable id surfaced to the frontend (the SDK call_id
                      when present, otherwise a synthesised UUID).
        name:         Function name (only the first chunk carries this).
        args_buffer:  Per-chunk partial-JSON fragments. Joined with "" to
                      reconstruct the full argument string.
        agent:        author_name from the update — propagated into events.
        slot:         Monotonic insertion index. Used to find the most-
                      recently-opened call for empty-call_id deltas, and
                      to decide ordering for force-close on call switch.
        closed:       True once we have emitted TOOL_CALL_END for this call.
    """

    id: str
    name: str
    args_buffer: list[str] = field(default_factory=list)
    agent: str = ""
    slot: int = 0
    closed: bool = False

    def joined_args(self) -> str:
        """Concatenate buffered fragments into the full argument string."""
        return "".join(self.args_buffer)


class ToolCallBuffer:
    """Per-stream aggregator for SDK function_call content fragments.

    One instance owns one logical agent stream (orchestrator turn,
    summary call, or specialist run). The hosting layer creates a fresh
    buffer per ``agent.run(stream=True)`` invocation and calls
    ``flush_open_calls()`` once the loop exits.

    Concurrency: NOT thread-safe. Each stream loop runs on a single task
    so this is fine.
    """

    def __init__(self, *, emit_deltas: bool = True) -> None:
        # Active calls keyed by SDK call_id. Empty-call_id deltas attach
        # to the most-recently-opened, not-yet-closed entry.
        self._active: dict[str, _ActiveCall] = {}
        # Monotonic counter so we can identify the trailing open call.
        self._next_slot: int = 0
        # When False, DELTA events are suppressed and only START + END
        # are emitted. Used by single-update transient buffers to
        # preserve the legacy event-pair contract for callers that
        # don't manage a multi-update lifecycle.
        self._emit_deltas = emit_deltas

    # ── Public API ───────────────────────────────────────────────────────

    def ingest_function_call(
        self, content: Any, agent: str
    ) -> list[StreamEvent]:
        """Process one SDK function_call content fragment.

        Args:
            content:  SDK Content object with type='function_call'.
                      Fields read: call_id, name, arguments.
            agent:    author_name from the parent AgentResponseUpdate.

        Returns:
            Ordered list of StreamEvents to forward to the SSE transport.
            May be empty (e.g. an opening chunk with no argument bytes
            emits only START with no DELTA).
        """
        events: list[StreamEvent] = []
        call_id_raw = getattr(content, "call_id", None) or ""
        name_raw = getattr(content, "name", None) or ""
        args_raw = getattr(content, "arguments", None)
        # Coerce mapping arguments into a JSON string so the wire format is
        # uniform — downstream consumers always see arguments_delta as str.
        if args_raw is None:
            arg_fragment = ""
        elif isinstance(args_raw, str):
            arg_fragment = args_raw
        else:
            try:
                arg_fragment = json.dumps(args_raw)
            except (TypeError, ValueError):
                arg_fragment = ""

        if call_id_raw:
            # Opening fragment OR a continuation that re-asserts the call_id.
            existing = self._active.get(call_id_raw)
            if existing is None:
                # Fresh call — close any previously-open call from a
                # different slot first (parallel-call boundary).
                events.extend(self._close_trailing_open_call_for_new(call_id_raw))
                call = _ActiveCall(
                    id=call_id_raw,
                    name=name_raw,
                    agent=agent,
                    slot=self._next_slot,
                )
                self._next_slot += 1
                self._active[call_id_raw] = call
                events.append(self._make_start(call))
                if arg_fragment:
                    call.args_buffer.append(arg_fragment)
                    # Eager-close path — when the entire JSON arrives in
                    # one chunk, collapse to the legacy START → END
                    # contract (no DELTA). This preserves backward-compat
                    # for backends that batch the call into a single
                    # update; multi-chunk streams still emit DELTA per
                    # additional fragment via the empty-call_id branch
                    # below.
                    end = self._try_close(call)
                    if end is not None:
                        events.append(end)
                    elif self._emit_deltas:
                        events.append(self._make_delta(call, arg_fragment))
                return events

            if existing.closed:
                # The call_id is being reused after closure (rare retry).
                # Reset the buffer and emit a new START so the frontend
                # re-renders the box with fresh state.
                existing.args_buffer = []
                existing.closed = False
                existing.slot = self._next_slot
                self._next_slot += 1
                if name_raw:
                    existing.name = name_raw
                events.append(self._make_start(existing))
                if arg_fragment:
                    existing.args_buffer.append(arg_fragment)
                    end = self._try_close(existing)
                    if end is not None:
                        events.append(end)
                    elif self._emit_deltas:
                        events.append(self._make_delta(existing, arg_fragment))
                return events

            # Continuation chunk that re-asserts call_id — rare but safe.
            if arg_fragment:
                existing.args_buffer.append(arg_fragment)
                if self._emit_deltas:
                    events.append(self._make_delta(existing, arg_fragment))
            end = self._try_close(existing)
            if end is not None:
                events.append(end)
            return events
        # Empty call_id → append to the most-recently-opened, open call.
        target = self._trailing_open_call()
        if target is None:
            # Orphan delta — log once at WARNING and drop. This indicates
            # an SDK fragment arrived before any opener (or after the
            # parent buffer was flushed). Dropping is safer than allocating
            # a phantom call the frontend cannot correlate.
            if arg_fragment:
                logger.warning(
                    "event_mapping.orphan_delta: dropping %d bytes (no active call)",
                    len(arg_fragment),
                )
            return events
        if arg_fragment:
            target.args_buffer.append(arg_fragment)
            if self._emit_deltas:
                events.append(self._make_delta(target, arg_fragment))
        end = self._try_close(target)
        if end is not None:
            events.append(end)
        return events

    def flush_open_calls(self) -> list[StreamEvent]:
        """Force-close every still-open call at stream end.

        Each open call gets a single TOOL_CALL_END whose ``arguments``
        is the parsed dict if the buffer happens to be valid JSON, or
        ``{}`` otherwise (with a WARNING log). Idempotent — subsequent
        calls return [].
        """
        events: list[StreamEvent] = []
        for call in list(self._active.values()):
            if call.closed:
                continue
            joined = call.joined_args()
            try:
                parsed: Any = json.loads(joined) if joined else {}
            except (json.JSONDecodeError, TypeError):
                # Includes the legacy phrase 'falling back to empty dict'
                # so existing log-assertion tests keep passing.
                logger.warning(
                    "event_mapping.unflushed_call_at_stream_end: id=%s name=%s buffer_len=%d "
                    "— falling back to empty dict",
                    call.id,
                    call.name,
                    len(joined),
                )
                parsed = {}
            if not isinstance(parsed, dict):
                parsed = {"value": parsed}
            call.closed = True
            events.append(StreamEvent(
                event=StreamEventType.TOOL_CALL_END,
                data={
                    "id": call.id,
                    "name": call.name,
                    "arguments": parsed,
                    "agent": call.agent,
                },
            ))
        return events

    # ── Internal helpers ─────────────────────────────────────────────────

    def _trailing_open_call(self) -> _ActiveCall | None:
        """Return the most-recently-opened, not-yet-closed call (or None)."""
        candidates = [c for c in self._active.values() if not c.closed]
        if not candidates:
            return None
        candidates.sort(key=lambda c: c.slot, reverse=True)
        return candidates[0]

    def _close_trailing_open_call_for_new(
        self, new_call_id: str
    ) -> list[StreamEvent]:
        """Force-close the trailing open call when a new call_id arrives.

        The OpenAI streaming protocol signals a new tool call by emitting
        a chunk with a non-empty `call_id` distinct from the prior one.
        Treat that as the implicit close of any outstanding call so the
        frontend sees a clean START → END before the new call's START.
        """
        events: list[StreamEvent] = []
        target = self._trailing_open_call()
        if target is None or target.id == new_call_id:
            return events
        joined = target.joined_args()
        try:
            parsed: Any = json.loads(joined) if joined else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "event_mapping.unparsed_args_at_close: id=%s name=%s buffer_len=%d",
                target.id,
                target.name,
                len(joined),
            )
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}
        target.closed = True
        events.append(StreamEvent(
            event=StreamEventType.TOOL_CALL_END,
            data={
                "id": target.id,
                "name": target.name,
                "arguments": parsed,
                "agent": target.agent,
            },
        ))
        return events

    def _try_close(self, call: _ActiveCall) -> StreamEvent | None:
        """If the buffered args parse as valid JSON, emit TOOL_CALL_END.

        Returns the event when the call is closed, otherwise None. This
        is the eager-close path: when a chunk contains the closing brace
        of the JSON document we can finalise the call immediately rather
        than waiting for the next call's opening or for stream end.
        """
        if call.closed:
            return None
        joined = call.joined_args()
        if not joined:
            return None
        try:
            parsed = json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(parsed, dict):
            # OpenAI tool args are always JSON objects in practice. Wrap
            # any other JSON value so the downstream contract (dict)
            # holds. This branch is defensive — should not occur with
            # the OpenAI / Azure OpenAI Chat Completions API.
            parsed = {"value": parsed}
        call.closed = True
        return StreamEvent(
            event=StreamEventType.TOOL_CALL_END,
            data={
                "id": call.id,
                "name": call.name,
                "arguments": parsed,
                "agent": call.agent,
            },
        )

    def _make_start(self, call: _ActiveCall) -> StreamEvent:
        """Build a TOOL_CALL_START event for the given call."""
        return StreamEvent(
            event=StreamEventType.TOOL_CALL_START,
            data={"id": call.id, "name": call.name, "agent": call.agent},
        )

    def _make_delta(self, call: _ActiveCall, fragment: str) -> StreamEvent:
        """Build a TOOL_CALL_DELTA event carrying one argument fragment."""
        return StreamEvent(
            event=StreamEventType.TOOL_CALL_DELTA,
            data={
                "id": call.id,
                "name": call.name,
                "arguments_delta": fragment,
                "agent": call.agent,
            },
        )


# ── Top-level mapper ────────────────────────────────────────────────────────


def map_update_to_events(
    update: Any,
    usage: dict[str, int],
    *,
    call_buffer: ToolCallBuffer | None = None,
) -> list[StreamEvent]:
    """Convert an AgentResponseUpdate to a list of StreamEvents.

    Maps the SDK's streaming update objects to the app's SSE event protocol:
    - Text content → TOKEN events
    - function_call content → TOOL_CALL_START / TOOL_CALL_DELTA / TOOL_CALL_END
      events via the supplied ToolCallBuffer (or a transient one if absent).
    - function_result content → TOOL_RESULT events
    - usage content → updates the usage accumulator (no event emitted)

    Args:
        update:       A single streaming update from agent.run(stream=True).
        usage:        Mutable dict with keys 'input', 'output', 'total'.
                      Updated in-place when usage content is encountered.
        call_buffer:  Per-stream tool-call aggregator. When None, a fresh
                      transient buffer is allocated for this single update
                      — preserves the legacy single-chunk-full-args behaviour
                      for callers that have not yet adopted the buffer
                      lifecycle (and for unit tests).

    Returns:
        List of StreamEvent objects to yield to the SSE transport.
    """
    events: list[StreamEvent] = []
    author = update.author_name or "NetworkOpsAgent"
    # Caller-supplied buffer means the consumer manages multi-update
    # lifecycle (the standard path during agent.run streaming). When
    # absent, allocate a transient buffer scoped to this single update
    # and auto-flush at the end so single-update callers preserve the
    # legacy START → END contract for any call whose JSON did not close
    # cleanly within this update.
    transient = call_buffer is None
    buf = call_buffer if call_buffer is not None else ToolCallBuffer(emit_deltas=False)

    # Text token
    if update.text:
        events.append(StreamEvent(
            event=StreamEventType.TOKEN,
            data={"token": update.text, "agent": author},
        ))

    # Content objects (tool calls, results, usage)
    for content in (update.contents or []):
        ct = getattr(content, "type", "")
        logger.debug("event_mapping.content: type=%s", ct)

        if ct == "function_call":
            events.extend(buf.ingest_function_call(content, author))

        elif ct == "function_result":
            events.append(StreamEvent(
                event=StreamEventType.TOOL_RESULT,
                data={
                    "id": content.call_id or "",
                    "name": content.name or "",
                    "result": str(content.result or ""),
                    "agent": author,
                },
            ))

        elif ct == "usage":
            extract_usage(content, usage)

        elif ct and ct not in ("text", "text_reasoning"):
            # Surface any unrecognised server tool content (web_search, etc.)
            # as a synthetic START + END pair so the frontend can render
            # them. These never stream args, so no DELTA is emitted.
            call_id = getattr(content, "call_id", None) or f"call_{uuid.uuid4().hex[:12]}"
            name = getattr(content, "name", None) or ct
            result = getattr(content, "result", None)
            events.append(StreamEvent(
                event=StreamEventType.TOOL_CALL_START,
                data={"id": call_id, "name": name, "agent": author},
            ))
            args_raw = getattr(content, "arguments", None) or {}
            if isinstance(args_raw, str):
                try:
                    args_raw = json.loads(args_raw)
                except (json.JSONDecodeError, TypeError):
                    args_raw = {"query": args_raw} if args_raw else {}
            events.append(StreamEvent(
                event=StreamEventType.TOOL_CALL_END,
                data={"id": call_id, "name": name,
                      "arguments": args_raw, "agent": author},
            ))
            # If the content already includes a result, emit it too
            if result is not None:
                events.append(StreamEvent(
                    event=StreamEventType.TOOL_RESULT,
                    data={"id": call_id, "name": name,
                          "result": str(result), "agent": author},
                ))

    if transient:
        # Drain any tool call still open at the end of this single
        # update so the legacy single-call contract holds.
        events.extend(buf.flush_open_calls())

    return events


def extract_usage(content: Any, usage: dict[str, int]) -> None:
    """Extract token usage from an SDK usage content object.

    Handles both dict-style and object-style access patterns for
    usage_details. Updates the usage accumulator dict in-place.

    Args:
        content: SDK content object with type='usage' and usage_details field.
        usage: Mutable dict with keys 'input', 'output', 'total'.
               Updated in-place when usage content is encountered.
    """
    raw = getattr(content, "usage_details", None) or {}
    if isinstance(raw, dict):
        usage["input"] = raw.get("input_token_count", 0) or 0
        usage["output"] = raw.get("output_token_count", 0) or 0
        usage["total"] = raw.get("total_token_count", 0) or 0
    else:
        usage["input"] = getattr(raw, "input_token_count", 0) or 0
        usage["output"] = getattr(raw, "output_token_count", 0) or 0
        usage["total"] = getattr(raw, "total_token_count", 0) or 0
    logger.info(
        "token_usage: input=%d output=%d total=%d",
        usage["input"], usage["output"], usage["total"],
    )


def extract_user_message(messages: list[dict]) -> str:
    """Extract the most recent user message from the conversation list.

    Scans the message list in reverse to find the last message with
    role='user'. Returns empty string if none found.

    Args:
        messages: OpenAI-format message dicts from the context window.

    Returns:
        The user message content string, or empty string.
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return msg.get("content", "")
    return ""
