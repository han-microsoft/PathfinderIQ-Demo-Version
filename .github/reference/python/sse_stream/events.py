"""events — the canonical SSE stream contract. Stdlib only.

The wire vocabulary every agent-streaming surface shares, plus the guaranteed
event order. Lifted from a production agentkit (pydantic BaseModel there; a
stdlib dataclass here to honour the seed's zero-dep rule). The contract is the
same; the validation library is not the point.

Guaranteed order (enforced by probe.check_event_sequence):
    no tools:  TOKEN* -> METADATA -> DONE
    w/ tools:  TOKEN* -> (TOOL_CALL_START -> TOOL_CALL_DELTA* -> TOOL_CALL_END
                          -> TOOL_RESULT?)* -> TOKEN* -> METADATA -> DONE
    failure:   ... -> ERROR        (terminal)
    abort:     ... -> ABORTED      (terminal)
Exactly one terminal frame; nothing follows it; METADATA precedes DONE.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class StreamEventType(str, Enum):
    """The wire vocabulary. str-Enum so `.value` is the on-wire event name."""

    TOKEN = "token"                      # text chunk from the assistant
    TOOL_CALL_START = "tool_call_start"  # a tool call opened (id, name)
    TOOL_CALL_DELTA = "tool_call_delta"  # partial JSON argument fragment
    TOOL_CALL_END = "tool_call_end"      # tool call closed (arguments: dict)
    TOOL_RESULT = "tool_result"          # tool returned a result
    METADATA = "metadata"                # usage + cost, precedes DONE
    DONE = "done"                        # success terminal
    ERROR = "error"                      # failure terminal
    ABORTED = "aborted"                  # client-cancel terminal
    RATE_LIMITED = "rate_limited"        # transient, not terminal (will retry)
    KEEPALIVE = "keepalive"              # heartbeat during silence


GENERIC_TERMINALS = frozenset({"done", "error", "aborted"})


def known_event_names() -> frozenset[str]:
    """The legal event vocabulary. Extend by unioning your domain names."""
    return frozenset(e.value for e in StreamEventType)


@dataclass
class StreamEvent:
    """One frame on the wire. `data` is the JSON-serializable payload."""

    event: StreamEventType
    data: dict = field(default_factory=dict)

    def to_wire(self) -> tuple[str, str]:
        """Render to (event_name, json_data) — the shape the probe checks."""
        return self.event.value, json.dumps(self.data, separators=(",", ":"))


__all__ = ["StreamEventType", "StreamEvent", "GENERIC_TERMINALS",
           "known_event_names"]
