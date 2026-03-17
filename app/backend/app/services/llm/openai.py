"""OpenAI-compatible LLM provider.

Module role:
    Implements the LLMService protocol using the OpenAI Python SDK’s streaming
    chat-completion API. Works with any provider implementing the standard
    ``POST /v1/chat/completions`` streaming protocol:
      - OpenAI (official)
      - Azure OpenAI
      - Ollama, vLLM, LM Studio, Mistral, LiteLLM, etc.

Configuration (from ``app.config.settings``):
    ``llm_base_url``  — API base URL (empty = official OpenAI)
    ``llm_api_key``   — API key
    ``llm_model``     — Model name or deployment name

Streaming protocol:
    The SDK’s ``stream=True`` yields ``ChatCompletionChunk`` objects. This
    service maps them to the app’s ``StreamEvent`` types: TOKEN for text
    deltas, TOOL_CALL_START/DELTA/END for function calls, METADATA for
    usage stats, and DONE/ERROR/ABORTED for terminal states.

Key collaborators:
    - ``openai.AsyncOpenAI`` – the async HTTP client for the OpenAI API
    - ``app.models.StreamEvent`` – yield type consumed by router_chat.py

Dependents:
    Created by: ``llm.py:create_llm_service()`` when ``LLM_PROVIDER=openai``
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.foundation.config import settings

logger = logging.getLogger(__name__)
from app.foundation.models import StreamEvent, StreamEventType, StreamMetadata


class OpenAILLMService:

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": settings.llm_api_key or "unused"}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url

        self._client = AsyncOpenAI(**kwargs)
        self._model = settings.llm_model

    async def stream_completion(
        self,
        messages: list[dict],
        *,
        abort_event: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        start = time.monotonic()
        assistant_id = uuid.uuid4().hex

        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=settings.max_response_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )

            tool_calls_in_progress: dict[int, dict[str, Any]] = {}

            async for chunk in stream:
                if abort_event and abort_event.is_set():
                    await stream.close()
                    yield StreamEvent(event=StreamEventType.ABORTED)
                    return

                choice = chunk.choices[0] if chunk.choices else None

                if choice is None:
                    if chunk.usage:
                        elapsed = (time.monotonic() - start) * 1000
                        from app.llmops._cost import estimate_cost
                        cost = estimate_cost(
                            self._model,
                            chunk.usage.prompt_tokens,
                            chunk.usage.completion_tokens,
                        )
                        yield StreamEvent(
                            event=StreamEventType.METADATA,
                            data=StreamMetadata(
                                prompt_tokens=chunk.usage.prompt_tokens,
                                completion_tokens=chunk.usage.completion_tokens,
                                total_tokens=chunk.usage.total_tokens,
                                duration_ms=elapsed,
                                model=self._model,
                                assistant_message_id=assistant_id,
                                estimated_cost_usd=cost,
                            ).model_dump(),
                        )
                    continue

                delta = choice.delta

                if delta.content:
                    yield StreamEvent(
                        event=StreamEventType.TOKEN,
                        data={"token": delta.content},
                    )

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_in_progress:
                            tool_calls_in_progress[idx] = {
                                "id": tc_delta.id or f"call_{uuid.uuid4().hex[:12]}",
                                "name": "",
                                "arguments": "",
                            }
                        tc = tool_calls_in_progress[idx]

                        if tc_delta.function:
                            if tc_delta.function.name:
                                tc["name"] = tc_delta.function.name
                                yield StreamEvent(
                                    event=StreamEventType.TOOL_CALL_START,
                                    data={"id": tc["id"], "name": tc["name"]},
                                )
                            if tc_delta.function.arguments:
                                tc["arguments"] += tc_delta.function.arguments
                                yield StreamEvent(
                                    event=StreamEventType.TOOL_CALL_DELTA,
                                    data={
                                        "id": tc["id"],
                                        "arguments_delta": tc_delta.function.arguments,
                                    },
                                )

                if choice.finish_reason:
                    for tc in tool_calls_in_progress.values():
                        try:
                            parsed_args = json.loads(tc["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            parsed_args = {}
                        yield StreamEvent(
                            event=StreamEventType.TOOL_CALL_END,
                            data={
                                "id": tc["id"],
                                "name": tc["name"],
                                "arguments": parsed_args,
                            },
                        )

        except asyncio.CancelledError:
            # Never swallow async cancellation — let it propagate
            raise
        except Exception as exc:
            # Classify the error to give the frontend an actionable message
            # instead of raw Python exception text.
            import openai as _openai  # Module cached in sys.modules; negligible cost
            if isinstance(exc, _openai.RateLimitError):
                logger.warning("OpenAI rate limit: %s", exc)
                yield StreamEvent(
                    event=StreamEventType.RATE_LIMITED,
                    data={"retry_after": 15},
                )
            elif isinstance(exc, _openai.APITimeoutError):
                logger.error("OpenAI timeout: %s", exc)
                yield StreamEvent(
                    event=StreamEventType.ERROR,
                    data={"error": "LLM request timed out. Please retry."},
                )
            elif isinstance(exc, _openai.AuthenticationError):
                logger.error("OpenAI auth error: %s", exc)
                yield StreamEvent(
                    event=StreamEventType.ERROR,
                    data={"error": "LLM authentication failed. Check API key."},
                )
            elif isinstance(exc, _openai.APIError):
                logger.exception("OpenAI API error")
                yield StreamEvent(
                    event=StreamEventType.ERROR,
                    data={"error": f"LLM error: {getattr(exc, 'message', str(exc))}"},
                )
            else:
                logger.exception("Unexpected error in OpenAI streaming")
                yield StreamEvent(
                    event=StreamEventType.ERROR,
                    data={"error": "An unexpected error occurred."},
                )
            return

        yield StreamEvent(event=StreamEventType.DONE)
