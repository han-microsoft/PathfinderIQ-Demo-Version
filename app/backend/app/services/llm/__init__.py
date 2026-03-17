"""LLM service protocol, factory, and lightweight dev providers.

Module role:
    Defines the ``LLMService`` protocol (interface) that all LLM providers
    must implement, provides a factory function that reads
    ``settings.llm_provider`` to instantiate the correct implementation,
    and contains the lightweight ``EchoLLMService`` and ``MockLLMService``
    dev providers inline (each is trivially small, no external dependencies).

    This is the only file consumers need to import. Route handlers and
    the dependency injection layer depend on the protocol, not on any
    concrete provider class.

Provider implementations:
    - ``openai.py``      — OpenAI-compatible (works with OpenAI, Azure OpenAI, vLLM, etc.)
    - ``agent.py``       — Azure AI Agent Framework (scenario-driven, with tools)
    - ``EchoLLMService`` — inline below (parrots the user message)
    - ``MockLLMService`` — inline below (canned rich response with tool calls)

Key collaborators:
    - ``app.config.settings.llm_provider`` – selects which provider to instantiate
    - ``app.models.StreamEvent``           – the yield type of ``stream_completion``

Dependents:
    Called by: ``main.py`` (factory), ``routers/chat.py`` (protocol)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from app.foundation.config import settings
from app.foundation.models import StreamEvent, StreamEventType, StreamMetadata


@runtime_checkable
class LLMService(Protocol):
    """Interface for LLM providers.

    Implementations are async generators yielding ``StreamEvent`` objects.
    Each provider must implement ``stream_completion`` which takes a list
    of OpenAI-format message dicts and an optional abort event for
    user-initiated cancellation.

    The generator must yield a terminal event (DONE, ERROR, or ABORTED)
    as its final event before returning.
    """

    async def stream_completion(
        self,
        messages: list[dict],
        *,
        abort_event: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


def create_llm_service() -> LLMService:
    """Instantiate the LLM service specified by ``settings.llm_provider``.

    Returns:
        An LLMService implementation. Lazy-imports heavy provider modules
        to avoid import-time failures for providers with heavy dependencies
        (e.g., agent-framework, azure-identity). Echo and Mock are defined
        inline in this file — no import needed.

    Raises:
        ImportError: If the selected provider's dependencies are not installed.
    """
    match settings.llm_provider:
        case "echo":
            return EchoLLMService()
        case "mock":
            return MockLLMService()
        case "agent":
            from app.services.llm.agent import AgentFrameworkService
            return AgentFrameworkService()
        case _:
            from app.services.llm.openai import OpenAILLMService
            return OpenAILLMService()


# ── Echo provider (inline — no external dependencies) ────────────────────────


class EchoLLMService:
    """Echoes the user's message back, token by token.

    The simplest possible LLMService. Parrots the user's last message
    prefixed with "Echo: ", streaming word-by-word with 50ms delays.
    Uses: frontend dev, integration tests, latency testing.
    """

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


# ── Mock provider (inline — canned rich response) ────────────────────────────


def _tokenize_mock(text: str) -> list[str]:
    """Split text on word boundaries, preserving whitespace and newlines."""
    tokens: list[str] = []
    current = ""
    for char in text:
        if char in (" ", "\n"):
            if current:
                tokens.append(current)
                current = ""
            tokens.append(char)
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


# Canned response exercising all UI rendering features
_MOCK_RESPONSE: dict[str, Any] = {
    "text": (
        "Here's everything I can do in a single response!\n\n"
        "## Markdown Rendering\n\n"
        "I support **bold**, *italic*, `inline code`, and ~~strikethrough~~.\n\n"
        "### Bullet Lists\n"
        "- First item\n"
        "- Second item with **emphasis**\n"
        "- Third item with `code`\n\n"
        "### Numbered Lists\n"
        "1. Step one\n"
        "2. Step two\n"
        "3. Step three\n\n"
        "### Blockquote\n"
        "> This is a blockquote. It can contain **bold** and `code` too.\n\n"
        "### Table\n\n"
        "| Service | Status | Latency |\n"
        "|---------|--------|---------|\n"
        "| API Gateway | 🟢 Healthy | 42ms |\n"
        "| Database | 🟢 Healthy | 8ms |\n"
        "| Cache | 🟡 Degraded | 120ms |\n\n"
        "---\n\n"
        "## Code Blocks\n\n"
        "Python:\n"
        "```python\n"
        "async def fetch_user(user_id: str) -> dict | None:\n"
        '    """Fetch a user by ID."""\n'
        "    row = await db.fetchrow(\n"
        '        \"SELECT * FROM users WHERE id = $1\",\n'
        "        user_id,\n"
        "    )\n"
        "    return dict(row) if row else None\n"
        "```\n\n"
        "TypeScript:\n"
        "```typescript\n"
        "async function fetchUser(userId: string): Promise<User | null> {\n"
        "  const row = await db.query(\n"
        "    'SELECT * FROM users WHERE id = $1',\n"
        "    [userId]\n"
        "  );\n"
        "  return row.rows[0] ?? null;\n"
        "}\n"
        "```\n\n"
        "---\n\n"
        "Now let me demonstrate **tool calls** — I'll search the docs, "
        "create a file, and run a command."
    ),
    "tool_calls": [
        {
            "name": "search_documentation",
            "arguments": {"query": "WebSocket connection lifecycle", "limit": 5},
            "result": '{"matches":[{"title":"WebSocket API","path":"docs/api/websocket.md","score":0.94},{"title":"Connection Manager","path":"docs/arch/connections.md","score":0.87}]}',
            "duration": 0.8,
        },
        {
            "name": "read_file",
            "arguments": {"path": "src/websocket/handler.ts", "start_line": 1, "end_line": 20},
            "result": 'export class ConnectionManager {\n  private conns = new Map<string, WebSocket>();\n\n  connect(ws: WebSocket, id: string) {\n    this.conns.set(id, ws);\n    ws.on("close", () => this.conns.delete(id));\n  }\n\n  broadcast(msg: string) {\n    for (const [, ws] of this.conns) {\n      if (ws.readyState === WebSocket.OPEN) ws.send(msg);\n    }\n  }\n}',
            "duration": 0.3,
        },
        {
            "name": "create_file",
            "arguments": {
                "path": "tests/test_ws.py",
                "content": "import pytest\n\n@pytest.mark.asyncio\nasync def test_connect():\n    mgr = ConnectionManager()\n    assert len(mgr.conns) == 0\n",
            },
            "result": '{"status":"created","path":"tests/test_ws.py","bytes":128}',
            "duration": 0.2,
        },
        {
            "name": "run_command",
            "arguments": {"command": "pytest tests/test_ws.py -v", "timeout": 30},
            "result": '{"exit_code":0,"stdout":"tests/test_ws.py::test_connect PASSED\\n\\n1 passed in 0.12s","stderr":""}',
            "duration": 1.5,
        },
    ],
    "after_tool": (
        "## Results\n\n"
        "All tools executed successfully:\n\n"
        "- ✅ Found 2 matching docs for WebSocket lifecycle\n"
        "- ✅ Read `ConnectionManager` source (13 lines)\n"
        "- ✅ Created `tests/test_ws.py` (128 bytes)\n"
        "- ✅ Tests passed: **1 passed in 0.12s**\n\n"
        "```\n"
        "tests/test_ws.py::test_connect PASSED\n"
        "\n"
        "1 passed in 0.12s\n"
        "```\n\n"
        "That covers markdown, code blocks, tables, blockquotes, "
        "tool calls with results, and post-tool analysis — all in one response."
    ),
}


class MockLLMService:
    """Canned rich response demonstrating all UI rendering capabilities.

    Streams markdown, code blocks, tables, tool calls with results, and
    post-tool text. No API keys or network access required.
    Uses: frontend development, demos, SSE pipeline testing.
    """

    async def stream_completion(
        self,
        messages: list[dict],
        *,
        abort_event: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        assistant_id = uuid.uuid4().hex
        start = time.monotonic()
        total_text = ""

        # Main text
        text = _MOCK_RESPONSE["text"]
        total_text += text
        for token in _tokenize_mock(text):
            if abort_event and abort_event.is_set():
                yield StreamEvent(event=StreamEventType.ABORTED)
                return
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": token})
            await asyncio.sleep(0.03)

        # Tool calls
        for tc in _MOCK_RESPONSE.get("tool_calls", []):
            tc_id = f"call_{uuid.uuid4().hex[:12]}"
            yield StreamEvent(
                event=StreamEventType.TOOL_CALL_START,
                data={"id": tc_id, "name": tc["name"]},
            )
            await asyncio.sleep(0.15)
            yield StreamEvent(
                event=StreamEventType.TOOL_CALL_END,
                data={"id": tc_id, "name": tc["name"], "arguments": tc["arguments"]},
            )
            await asyncio.sleep(tc.get("duration", 0.5))
            if "result" in tc:
                yield StreamEvent(
                    event=StreamEventType.TOOL_RESULT,
                    data={"id": tc_id, "name": tc["name"], "result": tc["result"]},
                )
                await asyncio.sleep(0.1)

        # Post-tool text
        after_tool = _MOCK_RESPONSE.get("after_tool", "")
        if after_tool:
            total_text += "\n\n" + after_tool
            yield StreamEvent(event=StreamEventType.TOKEN, data={"token": "\n\n"})
            await asyncio.sleep(0.05)
            for token in _tokenize_mock(after_tool):
                if abort_event and abort_event.is_set():
                    yield StreamEvent(event=StreamEventType.ABORTED)
                    return
                yield StreamEvent(event=StreamEventType.TOKEN, data={"token": token})
                await asyncio.sleep(0.03)

        # Metadata
        elapsed = (time.monotonic() - start) * 1000
        yield StreamEvent(
            event=StreamEventType.METADATA,
            data=StreamMetadata(
                prompt_tokens=len(total_text) // 4,
                completion_tokens=len(total_text) // 4,
                total_tokens=len(total_text) // 2,
                duration_ms=elapsed,
                model="mock",
                assistant_message_id=assistant_id,
            ).model_dump(),
        )
        yield StreamEvent(event=StreamEventType.DONE)
