"""probe — verify the SSE event-sequence contract. The executable spec.

Reference exemplar. Given the ordered wire frames a stream produced, assert the
invariants a correct stream must hold. This is what turns "I think the order is
right" into a checked fact (P7). Returns a list of failure strings — empty means
the contract held. Stdlib only.

Invariants checked:
    - every event name is in the allowed vocabulary;
    - no frame exceeds the byte cap;
    - every TOOL_CALL_END.id had a prior TOOL_CALL_START.id;
    - exactly one terminal frame (DONE | ERROR | ABORTED);
    - nothing follows the terminal frame;
    - a DONE terminal is preceded by METADATA.
"""
from __future__ import annotations

import json
from collections.abc import Iterable

from events import GENERIC_TERMINALS, known_event_names


def check_event_sequence(
    frames: Iterable[tuple[str, str]],
    *,
    max_frame_bytes: int = 1_000_000,
    allowed_events: frozenset[str] | None = None,
) -> list[str]:
    """Assert the generic SSE contract over (event_name, json_data) frames."""
    allowed = allowed_events if allowed_events is not None else known_event_names()
    failures: list[str] = []
    open_ids: set[str] = set()
    seen_metadata = False
    terminal: str | None = None
    post_terminal: list[str] = []

    for idx, (name, data_raw) in enumerate(frames):
        if terminal is not None:
            post_terminal.append(name)
            continue
        if name not in allowed:
            failures.append(f"frame {idx} event={name!r} not in allowed vocabulary")
        if len(data_raw.encode("utf-8")) > max_frame_bytes:
            failures.append(f"frame {idx} event={name!r} exceeds max_frame_bytes")
        try:
            data = json.loads(data_raw) if data_raw else {}
        except json.JSONDecodeError:
            failures.append(f"frame {idx} event={name!r} has invalid JSON data")
            data = {}

        if name == "tool_call_start":
            if data.get("id"):
                open_ids.add(data["id"])
        elif name == "tool_call_end":
            tid = data.get("id", "")
            if tid and tid not in open_ids:
                failures.append(
                    f"frame {idx} tool_call_end id={tid!r} has no prior start")
        elif name == "metadata":
            seen_metadata = True
        elif name in GENERIC_TERMINALS:
            terminal = name

    if terminal is None:
        failures.append("stream ended with no terminal frame (done/error/aborted)")
    if post_terminal:
        failures.append(f"events after terminal frame: {post_terminal!r}")
    if terminal == "done" and not seen_metadata:
        failures.append("done terminal not preceded by metadata")
    return failures


__all__ = ["check_event_sequence"]
