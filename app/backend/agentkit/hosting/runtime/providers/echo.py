"""Echo LLM provider — parrots the user's message, token by token.

The simplest possible streaming-LLM implementation. Parrots the user's
last message prefixed with "Echo: ", streaming word-by-word with 50ms
delays. Uses: frontend dev, integration tests, latency testing.

Imports ``agentkit.contracts.models`` and stdlib only.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType, StreamMetadata


class EchoLLMService:
    """Echoes the user's message back, token by token."""

    async def stream_completion(
        self,
        messages: list[dict],
        *,
        abort_event: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        # Extract last user message
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        reply = f"Echo: {user_msg}" if user_msg else "Echo: (empty message)"
        assistant_id = uuid.uuid4().hex

        # Stream word-by-word with small delay
        words = reply.split()
        for i, word in enumerate(words):
            if abort_event and abort_event.is_set():
                yield StreamEvent(event=StreamEventType.ABORTED)
                return
            token = word if i == 0 else f" {word}"
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": token})
            await asyncio.sleep(0.05)

        yield StreamEvent(
            event=StreamEventType.METADATA,
            data=StreamMetadata(
                prompt_tokens=len(reply) // 4,
                completion_tokens=len(reply) // 4,
                total_tokens=len(reply) // 2,
                duration_ms=len(words) * 50,
                model="echo",
                assistant_message_id=assistant_id,
            ).model_dump(),
        )
        yield StreamEvent(event=StreamEventType.DONE)


__all__ = ["EchoLLMService"]
