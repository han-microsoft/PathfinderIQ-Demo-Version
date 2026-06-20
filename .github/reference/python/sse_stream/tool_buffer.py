"""tool_buffer — aggregate streamed tool-call fragments. The hard part.

Reference exemplar. Lifted near-verbatim from a production agentkit (byte-
identical across two independent projects). An LLM streams a tool call as many
chunks: an opener with `call_id` + `name`, then argument-JSON fragments that may
arrive under the same `call_id` OR under an empty `call_id` (attach to the most-
recently-opened call). A naive implementation drops fragments, mis-orders
parallel calls, or never closes a call. This buffer gets it right.

Guarantees the per-call lifecycle START -> DELTA* -> END:
    - eager close when buffered args parse as valid JSON;
    - force-close the trailing open call when a NEW call_id arrives (parallel
      call boundary);
    - flush any still-open call at stream end (END with {} if args never closed).

Not thread-safe by design: one buffer per single-task stream loop.
Stdlib only. Duck-typed: reads call_id/name/arguments off any object.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from events import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


@dataclass
class _ActiveCall:
    id: str
    name: str
    args_buffer: list[str] = field(default_factory=list)
    slot: int = 0          # monotonic open index — finds the trailing open call
    closed: bool = False

    def joined_args(self) -> str:
        return "".join(self.args_buffer)


class ToolCallBuffer:
    def __init__(self, *, emit_deltas: bool = True) -> None:
        self._active: dict[str, _ActiveCall] = {}
        self._next_slot = 0
        self._emit_deltas = emit_deltas

    def ingest_function_call(self, content: Any, agent: str = "") -> list[StreamEvent]:
        """Process one streamed function_call fragment -> ordered events."""
        events: list[StreamEvent] = []
        call_id = getattr(content, "call_id", None) or ""
        name = getattr(content, "name", None) or ""
        frag = _coerce_args(getattr(content, "arguments", None))

        if call_id:
            existing = self._active.get(call_id)
            if existing is None:
                # New call: close any trailing open call first (parallel boundary).
                events.extend(self._close_trailing_for_new(call_id))
                call = _ActiveCall(id=call_id, name=name, slot=self._next_slot)
                self._next_slot += 1
                self._active[call_id] = call
                events.append(self._start(call, agent))
                if frag:
                    call.args_buffer.append(frag)
                    end = self._try_close(call, agent)
                    if end is not None:
                        events.append(end)          # eager close (full JSON in one chunk)
                    elif self._emit_deltas:
                        events.append(self._delta(call, frag, agent))
                return events
            # Continuation re-asserting the same call_id.
            if frag:
                existing.args_buffer.append(frag)
                if self._emit_deltas:
                    events.append(self._delta(existing, frag, agent))
            end = self._try_close(existing, agent)
            if end is not None:
                events.append(end)
            return events

        # Empty call_id -> append to the most-recently-opened, open call.
        target = self._trailing_open()
        if target is None:
            if frag:
                logger.warning("orphan tool-call delta dropped: %d bytes", len(frag))
            return events
        if frag:
            target.args_buffer.append(frag)
            if self._emit_deltas:
                events.append(self._delta(target, frag, agent))
        end = self._try_close(target, agent)
        if end is not None:
            events.append(end)
        return events

    def flush_open_calls(self, agent: str = "") -> list[StreamEvent]:
        """Force-close every still-open call at stream end. Idempotent."""
        events: list[StreamEvent] = []
        for call in list(self._active.values()):
            if call.closed:
                continue
            events.append(self._force_end(call, agent))
        return events

    # ── internals ────────────────────────────────────────────────────────

    def _trailing_open(self) -> _ActiveCall | None:
        opens = [c for c in self._active.values() if not c.closed]
        return max(opens, key=lambda c: c.slot) if opens else None

    def _close_trailing_for_new(self, new_id: str) -> list[StreamEvent]:
        target = self._trailing_open()
        if target is None or target.id == new_id:
            return []
        return [self._force_end(target, "")]

    def _force_end(self, call: _ActiveCall, agent: str) -> StreamEvent:
        joined = call.joined_args()
        try:
            parsed: Any = json.loads(joined) if joined else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning("unparsed args at close id=%s -> {}", call.id)
            parsed = {}
        return self._close(call, parsed, agent)

    def _try_close(self, call: _ActiveCall, agent: str) -> StreamEvent | None:
        joined = call.joined_args()
        if not joined:
            return None
        try:
            parsed = json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            return None  # JSON not complete yet — wait for more fragments
        return self._close(call, parsed, agent)

    def _close(self, call: _ActiveCall, parsed: Any, agent: str) -> StreamEvent:
        """Mark a call closed and build its TOOL_CALL_END (one home for the END)."""
        if not isinstance(parsed, dict):
            parsed = {"value": parsed}
        call.closed = True
        return StreamEvent(StreamEventType.TOOL_CALL_END,
                           {"id": call.id, "name": call.name,
                            "arguments": parsed, "agent": agent})

    def _start(self, call: _ActiveCall, agent: str) -> StreamEvent:
        return StreamEvent(StreamEventType.TOOL_CALL_START,
                           {"id": call.id, "name": call.name, "agent": agent})

    def _delta(self, call: _ActiveCall, frag: str, agent: str) -> StreamEvent:
        return StreamEvent(StreamEventType.TOOL_CALL_DELTA,
                           {"id": call.id, "name": call.name,
                            "arguments_delta": frag, "agent": agent})


def _coerce_args(raw: Any) -> str:
    """Normalize arguments to a JSON-string fragment (uniform wire format)."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw)
    except (TypeError, ValueError):
        return ""


def new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


__all__ = ["ToolCallBuffer", "new_call_id"]
