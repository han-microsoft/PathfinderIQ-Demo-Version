"""Pydantic models — the single source of truth for the API contract.

Module role:
    Defines every data shape that crosses the wire between frontend and backend.
    The frontend TypeScript types in ``api/types.ts`` mirror these models exactly.
    Any change here must be reflected in the frontend types.

Model groups:
    Enums       — Role, MessageStatus, StreamEventType
    Core Models — ToolCall, Message, Session, SessionSummary
    API I/O     — ChatRequest, CreateSessionRequest, UpdateSessionRequest
    SSE Events  — StreamEvent, StreamMetadata

Key collaborators:
    - ``api/types.ts``             – frontend mirror (must stay in sync)
    - ``router_chat.py``           – streams StreamEvent objects via SSE
    - ``session_store.py``         – persists Session and Message objects
    - ``API_CONTRACT.md``          – human-readable specification of these shapes

Dependents:
    Imported by every router, service, and store module in the backend.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Enums ────────────────────────────────────────────────────────────────────
# String enums serialised directly into JSON responses and SSE events.
# The string values must match what the frontend expects in api/types.ts.


class Role(str, Enum):
    """Message author roles — mirrors OpenAI chat-completion "role" values.

    Used by the context manager to classify messages when building the
    LLM input array, and by the frontend to choose rendering styles.
    """

    SYSTEM = "system"        # System instructions (never shown to user)
    USER = "user"            # Human-authored messages
    ASSISTANT = "assistant"  # LLM-generated responses
    TOOL = "tool"            # Tool execution results (OpenAI tool message format)


class MessageStatus(str, Enum):
    """Lifecycle status of a message.

    State machine: PENDING → STREAMING → COMPLETE | ERROR | ABORTED.
    The frontend uses this to decide whether to show a spinner, final
    content, or an error badge on a message bubble.
    """

    PENDING = "pending"      # User message sent, assistant has not started
    STREAMING = "streaming"  # Assistant response actively being generated
    COMPLETE = "complete"    # Final — content is fully assembled
    ERROR = "error"          # Generation failed (LLM error, network, etc.)
    ABORTED = "aborted"      # User-initiated cancellation via abort endpoint


class StreamEventType(str, Enum):
    """SSE event types sent during streaming.

    Sent as the ``event:`` field in SSE frames. The frontend's SSE parser
    switches on these values to dispatch to the correct callback.
    See API_CONTRACT.md for the event sequence and payload schemas.

    Normal flow:   TOKEN* → METADATA → DONE
    With tools:    TOKEN* → (TOOL_CALL_START → TOOL_CALL_END → TOOL_RESULT?)* → TOKEN* → DONE
    Error:         TOKEN* → ERROR
    Abort:         TOKEN* → ABORTED
    """

    TOKEN = "token"                      # Incremental text delta for response assembly
    TOOL_CALL_START = "tool_call_start"  # Tool invocation begins (shows tool name)
    TOOL_CALL_DELTA = "tool_call_delta"  # Incremental tool call argument chunk
    TOOL_CALL_END = "tool_call_end"      # Tool call fully assembled with parsed args
    TOOL_RESULT = "tool_result"          # Tool execution result string
    THINKING = "thinking"               # Chain-of-thought step (visible thinking UI)
    CITATION = "citation"               # Source citation reference
    ERROR = "error"                      # Terminal error — stream ends
    DONE = "done"                        # Terminal success — stream ends
    ABORTED = "aborted"                  # Terminal cancellation — stream ends
    METADATA = "metadata"                # Usage stats and timing (sent before DONE)
    RATE_LIMITED = "rate_limited"         # LLM rate-limited — retry countdown in progress
    KEEPALIVE = "keepalive"               # Heartbeat — keeps frontend idle-timeout from firing


# ── Tool Calls ───────────────────────────────────────────────────────────────


class ToolCall(BaseModel):
    """A tool/function call made by the assistant.

    Assembled during streaming from TOOL_CALL_START (id + name),
    TOOL_CALL_END (complete arguments), and TOOL_RESULT (execution output).
    Stored on the Message object for persistence and replay.

    Attributes:
        id: Unique call identifier (e.g., "call_abc123"). Auto-generated if omitted.
        name: Tool function name (e.g., "query_graph", "search_runbooks").
        arguments: Parsed JSON arguments passed to the tool.
        result: Raw string result from tool execution, or None if not yet executed.
    """

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    duration_ms: float | None = None  # Time from tool_call_start to tool_result


# ── Messages ─────────────────────────────────────────────────────────────────


class ContextSnapshot(BaseModel):
    """Record of exactly what context was sent to the LLM for an assistant message.

    Stored on assistant messages for auditability. The ``context_messages``
    field is optional — omitted by default when persisting to Cosmos (to
    save RU cost), always included in saved JSON files and in-memory store.

    Attributes:
        agent_session_id: Unique ID of the agent's SDK thread.
        agent_id: Config key of the agent (e.g. "orchestrator").
        system_prompt_chars: Character count of the system prompt.
        messages_total: Total messages in the thread before trimming.
        messages_kept: Messages kept after token-budget trimming.
        messages_dropped: Messages dropped by trimming.
        tokens_used: Tokens consumed by the kept messages.
        tokens_budget: Total token budget available.
        max_turns: Max conversation turns setting (None = unlimited).
        user_message: The user query this response answers.
        context_messages: The actual messages sent to the LLM (optional).
    """

    agent_session_id: str = ""
    agent_id: str = ""
    system_prompt_chars: int = 0
    messages_total: int = 0
    messages_kept: int = 0
    messages_dropped: int = 0
    tokens_used: int = 0
    tokens_budget: int = 0
    max_turns: int | None = None     # None = unlimited
    user_message: str = ""
    context_messages: list[dict[str, str]] | None = None  # Optional — omitted in Cosmos by default
    # Stream metadata — merged from METADATA SSE event for session metrics persistence
    model: str = ""
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class Message(BaseModel):
    """A single conversation message.

    Represents both user and assistant messages. During streaming, the
    assistant message is created with status=STREAMING, then updated to
    COMPLETE/ERROR/ABORTED when the stream terminates.

    The ``tool_calls`` list is assembled from SSE events during streaming
    and persisted for replay when loading a session from the store.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: Role
    content: str = ""
    status: MessageStatus = MessageStatus.COMPLETE
    tool_calls: list[ToolCall] = Field(default_factory=list)
    agent_name: str = ""           # Which agent authored this message (empty = single-agent)
    context_snapshot: ContextSnapshot | None = None  # Populated on assistant messages for auditing
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}


# ── Agent Threads ────────────────────────────────────────────────────────────


class AgentThread(BaseModel):
    """A per-agent conversation thread within a session.

    Each agent gets its own thread with a unique ``agent_session_id``.
    Message 0 is the system prompt (role=system) for auditability.
    Messages are appended chronologically and never reordered.

    Attributes:
        agent_session_id: Unique ID for this agent's SDK thread.
        agent_id: Config key (e.g. "orchestrator", "network_investigator").
        agent_name: Display name (e.g. "NOCOrchestrator").
        messages: Ordered message list. Message 0 is the system prompt.
        created_at: When this thread was first created.
    """

    agent_session_id: str = Field(
        default_factory=lambda: f"ast_{uuid.uuid4().hex[:12]}"
    )
    agent_id: str = ""
    agent_name: str = ""
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ── v2 → v3 Migration ────────────────────────────────────────────────────────


def migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v2 session dict (flat messages[]) to v3 (threads{}).

    Called by Session's model_validator before Pydantic constructs the object.
    Groups flat messages by agent_name into separate AgentThread entries.
    Messages with empty agent_name default to the "orchestrator" thread.

    Args:
        data: Raw session dict (from JSON or Cosmos doc).

    Returns:
        The dict with ``threads`` populated and ``messages`` removed.
        Returns as-is if already v3 or if ``threads`` key exists.

    Side effects:
        None — pure function.
    """
    # Already v3 or has threads — no migration needed
    if data.get("schema_version", 0) >= 3 or "threads" in data:
        return data

    # Group flat messages by agent_name
    flat_messages = data.pop("messages", [])
    threads: dict[str, dict[str, Any]] = {}
    for msg in flat_messages:
        # msg may be a raw dict (from JSON) or a Pydantic Message object
        # (from in-memory cloning). Normalize to dict for uniform access.
        if hasattr(msg, "model_dump"):
            msg = msg.model_dump(mode="json")
        # Determine agent_id from agent_name (empty → "orchestrator")
        agent_id = msg.get("agent_name", "") or "orchestrator"
        if agent_id not in threads:
            threads[agent_id] = {
                "agent_session_id": f"ast_{uuid.uuid4().hex[:12]}",
                "agent_id": agent_id,
                "agent_name": agent_id,
                "messages": [],
                "created_at": msg.get("created_at", datetime.now(timezone.utc).isoformat()),
            }
        threads[agent_id]["messages"].append(msg)

    data["threads"] = threads
    data["schema_version"] = 3
    return data


# ── Sessions ─────────────────────────────────────────────────────────────────


class Session(BaseModel):
    """A conversation session with per-agent threads (schema v3).

    Each session belongs to one scenario (recorded at creation time via
    ``scenario_name``). Conversation history is organized into per-agent
    threads keyed by agent_id. Each thread has its own message list,
    system prompt (message 0), and unique agent_session_id.

    The model_validator handles v2→v3 migration: if a flat ``messages[]``
    is detected, it groups messages by agent_name into ``threads{}``.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str = "New conversation"
    schema_version: int = 3        # Schema version — v3 = per-agent threads
    scenario_name: str = ""  # scenario active when session was created
    user_id: str = ""  # Entra oid of session owner. "__default__" = visible to all users.
    threads: dict[str, AgentThread] = Field(default_factory=dict)  # keyed by agent_id
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_schema(cls, data: Any) -> Any:
        """Auto-migrate v2 sessions (flat messages[]) to v3 (threads{})."""
        if isinstance(data, dict):
            return migrate_v2_to_v3(data)
        return data


class SessionSummary(BaseModel):
    """Lightweight session metadata for list views (no messages).

    Used by GET /api/sessions to return a compact session list without
    transferring full message histories. Rendered in the SessionSidebar.
    Includes per-session activity counts derived from message content.
    """

    id: str
    title: str
    scenario_name: str = ""  # scenario active when session was created
    user_id: str = ""  # Entra oid of session owner. "__default__" = visible to all users.
    message_count: int
    tool_call_count: int = 0     # total tool invocations across all messages
    thinking_count: int = 0      # number of thinking tool calls
    user_prompt_count: int = 0   # number of user messages
    agent_response_count: int = 0  # number of assistant messages
    created_at: datetime
    updated_at: datetime


# ── API Request / Response ───────────────────────────────────────────────────


class ChatRequest(BaseModel):
    """Client → Server: send a user message.

    The ``content`` field is validated to be 1–100,000 characters.
    Sent as POST body to /api/chat/{session_id}.

    ``max_context_turns`` controls how many past conversation turns are
    included in the LLM context. None = unlimited (token budget governs).
    """

    content: str = Field(..., min_length=1, max_length=100_000)
    max_context_turns: int | None = None  # None = unlimited (token budget governs)


class CreateSessionRequest(BaseModel):
    """Client → Server: create a new session."""

    title: str = "New conversation"


class UpdateSessionRequest(BaseModel):
    """Client → Server: update session metadata."""

    title: str


# ── SSE Event Payloads ───────────────────────────────────────────────────────


class StreamEvent(BaseModel):
    """A single SSE event sent during streaming.

    Created by LLM service implementations (llm/openai.py, llm/agent.py, etc.)
    and serialised into SSE wire format by ``_format_sse()`` in router_chat.py.
    Wire format: ``event: {type}\\ndata: {json}\\n\\n``.

    Attributes:
        event: The event type (determines how the frontend processes the data).
        data: Arbitrary JSON payload whose schema depends on the event type.
    """

    event: StreamEventType
    data: dict[str, Any] = Field(default_factory=dict)


class StreamMetadata(BaseModel):
    """Usage and timing metadata sent as the final METADATA event."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    model: str = ""
    assistant_message_id: str = ""
    estimated_cost_usd: float | None = None  # None when model not in pricing table
