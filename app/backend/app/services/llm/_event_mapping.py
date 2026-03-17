"""Agent event mapping — SDK AgentResponseUpdate → SSE StreamEvent.

Module role:
    Extracted from agent.py — converts Agent Framework SDK streaming updates
    into the app's SSE StreamEvent protocol. Also extracts token usage data
    from SDK usage content objects.

Key collaborators:
    - agent_framework.AgentResponseUpdate — SDK streaming update objects
    - app.models.StreamEvent, StreamEventType — SSE event protocol

Dependents:
    Called by: app.services.llm.agent.stream_completion()
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.foundation.models import StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


def map_update_to_events(
    update: Any,
    usage: dict[str, int],
) -> list[StreamEvent]:
    """Convert an AgentResponseUpdate to a list of StreamEvents.

    Maps the SDK's streaming update objects to the app's SSE event protocol:
    - Text content → TOKEN events
    - function_call content → TOOL_CALL_START + TOOL_CALL_END events
    - function_result content → TOOL_RESULT events
    - usage content → updates the usage accumulator (no event emitted)

    Args:
        update: A single streaming update from agent.run(stream=True).
        usage: Mutable dict with keys 'input', 'output', 'total'.
               Updated in-place when usage content is encountered.

    Returns:
        List of StreamEvent objects to yield to the SSE transport.
    """
    events: list[StreamEvent] = []
    author = update.author_name or "NetworkOpsAgent"

    # Text token
    if update.text:
        events.append(StreamEvent(
            event=StreamEventType.TOKEN,
            data={"token": update.text, "agent": author},
        ))

    # Content objects (tool calls, results, usage)
    for content in (update.contents or []):
        ct = getattr(content, "type", "")

        if ct == "function_call":
            call_id = content.call_id or f"call_{uuid.uuid4().hex[:12]}"
            args = content.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("tool_call.arguments parse failed: %s — falling back to {}", e)
                    args = {}
            events.append(StreamEvent(
                event=StreamEventType.TOOL_CALL_START,
                data={"id": call_id, "name": content.name or "", "agent": author},
            ))
            events.append(StreamEvent(
                event=StreamEventType.TOOL_CALL_END,
                data={"id": call_id, "name": content.name or "",
                      "arguments": args or {}, "agent": author},
            ))

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
