"""Generic live SSE contract-test harness (S2).

Module role:
    The domain-blind half of the SSE contract probe. Provides:

    - ``parse_sse_frames`` — a byte-line iterator → ``(event_name, data)``
      frame parser (handles SSE comment/keepalive lines and multi-line
      ``data:`` payloads).
    - ``check_event_sequence`` — asserts the generic event-sequence
      contract on a list of frames and returns a list of failure strings
      (empty = pass).

    The contract asserted (from ``specs/sse_event_contract.md``):
      * Exactly one terminal frame (``done`` | ``error`` | ``aborted``).
      * No frame follows the terminal.
      * Every ``tool_call_end.id`` has a matching prior ``tool_call_start.id``.
      * ``metadata`` precedes ``done`` when ``done`` is the terminal.
      * No frame's encoded ``data:`` exceeds the configured byte cap.
      * Every event name is ``known`` — generic core
        (``agentkit.hosting.sse.GENERIC_EVENT_NAMES``) or a name the
        consumer registered via ``register_domain_events``. This is the
        teeth of the vocabulary split: an unregistered event name on the
        wire is a contract failure.

Layer note:
    Imports ``agentkit.hosting.sse`` only (stdlib otherwise). The signing /
    transport / domain-trigger half of any concrete probe stays in the
    consumer's ``scripts/`` (it needs the consumer's auth + a domain-shaped
    chat trigger). This module is the reusable assertion core.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

from agentkit.hosting.sse import GENERIC_TERMINALS, known_event_names


def parse_sse_frames(lines: Iterable[bytes]) -> Iterator[tuple[str, str]]:
    """Yield ``(event_name, data_json_str)`` pairs from raw SSE byte lines.

    Args:
        lines: An iterable of raw bytes lines (e.g. an ``HTTPResponse``).
            SSE frames are separated by blank lines; ``data:`` may span
            multiple lines (joined with ``\\n``); lines starting with
            ``:`` are comment/keepalive pings and are ignored.

    Yields:
        One ``(event_name, data)`` tuple per complete frame that carries
        both an ``event:`` and at least one ``data:`` line.
    """
    event_name = ""
    data_buf: list[str] = []
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if event_name and data_buf:
                yield event_name, "\n".join(data_buf)
            event_name = ""
            data_buf = []
            continue
        if line.startswith(":"):
            # SSE comment frame (keepalive ping). Ignore.
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_buf.append(line[len("data:"):].lstrip(" "))
    # Trailing frame with no terminating blank line (rare but valid).
    if event_name and data_buf:
        yield event_name, "\n".join(data_buf)


def check_event_sequence(
    frames: list[tuple[str, str]],
    max_frame_bytes: int,
    *,
    allowed_events: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """Assert the generic SSE event-sequence contract.

    Args:
        frames: Ordered ``(event_name, data_json_str)`` pairs.
        max_frame_bytes: Upper bound on each frame's encoded ``data:`` UTF-8
            byte length.
        allowed_events: The legal event-name vocabulary. Defaults to
            ``known_event_names()`` (generic core ∪ consumer-registered
            domain names). Pass an explicit set to scope the check (e.g. a
            probe that imports the consumer's domain registration).

    Returns:
        A list of failure messages. Empty list means all assertions pass.
    """
    allowed = (
        frozenset(allowed_events) if allowed_events is not None else known_event_names()
    )
    failures: list[str] = []
    open_tool_ids: set[str] = set()
    closed_tool_ids: set[str] = set()
    seen_metadata = False
    terminal_seen: str | None = None
    post_terminal_events: list[str] = []

    for idx, (name, data_raw) in enumerate(frames):
        if terminal_seen is not None:
            post_terminal_events.append(name)
            continue
        # Vocabulary guard — the executable half of the §3.5 split.
        if name not in allowed:
            failures.append(
                f"frame {idx} event={name!r} is not a known event name "
                f"(generic core or registered domain)"
            )
        # Frame-size guard.
        if len(data_raw.encode("utf-8")) > max_frame_bytes:
            failures.append(
                f"frame {idx} event={name!r} exceeds max_frame_bytes "
                f"({len(data_raw.encode('utf-8'))} > {max_frame_bytes})"
            )
        try:
            data = json.loads(data_raw) if data_raw else {}
        except json.JSONDecodeError:
            failures.append(f"frame {idx} event={name!r} has invalid JSON data")
            data = {}
        if name == "tool_call_start":
            tid = data.get("id", "")
            if tid:
                open_tool_ids.add(tid)
        elif name == "tool_call_end":
            tid = data.get("id", "")
            if tid and tid not in open_tool_ids:
                failures.append(
                    f"frame {idx} tool_call_end id={tid!r} has no prior tool_call_start"
                )
            if tid:
                closed_tool_ids.add(tid)
        elif name == "metadata":
            seen_metadata = True
        elif name in GENERIC_TERMINALS:
            terminal_seen = name

    if terminal_seen is None:
        failures.append("stream ended with no terminal frame (DONE/ERROR/ABORTED)")
    if post_terminal_events:
        failures.append(
            f"events appear after terminal frame: {post_terminal_events!r}"
        )
    if terminal_seen == "done" and not seen_metadata:
        failures.append("DONE terminal not preceded by METADATA")
    return failures
