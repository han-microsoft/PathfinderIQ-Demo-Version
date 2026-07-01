"""mapper — SDK streaming update -> canonical StreamEvents. Duck-typed.

Reference exemplar. Reads an SDK update object purely by attribute (getattr),
never importing the SDK type (PATTERNS.md §4). One update may carry text and/or
content objects (tool calls, results, usage). Text -> TOKEN; function_call ->
the ToolCallBuffer; function_result -> TOOL_RESULT; usage -> accumulator (no
event). Stdlib only.

Expected (duck-typed) update shape:
    update.text            -> str | None         (assistant text chunk)
    update.author_name     -> str | None         (who produced it)
    update.contents        -> list | None         of content objects, each with:
        content.type       -> "function_call" | "function_result" | "usage" | ...
        function_call:  content.call_id, content.name, content.arguments
        function_result: content.call_id, content.name, content.result
        usage:          content.input, content.output
"""
from __future__ import annotations

from typing import Any

from events import StreamEvent, StreamEventType
from tool_buffer import ToolCallBuffer


def extract_usage(content: Any, usage: dict) -> None:
    """Accumulate token usage in-place from a usage content object."""
    usage["input"] = usage.get("input", 0) + (getattr(content, "input", 0) or 0)
    usage["output"] = usage.get("output", 0) + (getattr(content, "output", 0) or 0)
    usage["total"] = usage["input"] + usage["output"]


def map_update_to_events(update: Any, usage: dict, *,
                         call_buffer: ToolCallBuffer) -> list[StreamEvent]:
    """Convert one streaming update to its ordered StreamEvents."""
    events: list[StreamEvent] = []
    author = getattr(update, "author_name", None) or ""

    text = getattr(update, "text", None)
    if text:
        events.append(StreamEvent(StreamEventType.TOKEN,
                                  {"token": text, "agent": author}))

    for content in (getattr(update, "contents", None) or []):
        ctype = getattr(content, "type", "")
        if ctype == "function_call":
            events.extend(call_buffer.ingest_function_call(content, author))
        elif ctype == "function_result":
            events.append(StreamEvent(StreamEventType.TOOL_RESULT, {
                "id": getattr(content, "call_id", "") or "",
                "name": getattr(content, "name", "") or "",
                "result": str(getattr(content, "result", "") or ""),
                "agent": author,
            }))
        elif ctype == "usage":
            extract_usage(content, usage)
        # other content types are ignored by this minimal reference

    return events


__all__ = ["map_update_to_events", "extract_usage"]
