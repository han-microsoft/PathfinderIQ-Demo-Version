"""agentkit.contracts.models — generic agent-runtime wire contracts.

Module role:
    The domain-blind half of the conversation/wire model set. Holds the
    pydantic types every agent application needs on the wire: message roles +
    status, the SSE event type enum + ``StreamEvent`` envelope, tool-call and
    context-snapshot records, per-agent threads, and background-run records.

    GridIQ-specific models (``Session`` with its summary / priority-action
    state, situation summaries, detector request bodies) stay in the consumer
    (``foundation/models.py``) and import the generic pieces from here.

Layer rule:
    stdlib + pydantic only. Never imports a consumer package.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Enums ────────────────────────────────────────────────────────────────────


class Role(str, Enum):
    """Message author roles — mirrors OpenAI chat-completion "role" values."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageStatus(str, Enum):
    """Lifecycle status of a message.

    State machine: PENDING → STREAMING → COMPLETE | ERROR | ABORTED.
    """

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETE = "complete"
    ERROR = "error"
    ABORTED = "aborted"


class AgentRunStatus(str, Enum):
    """Lifecycle state for a first-class background agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    ABORTED = "aborted"


class StreamEventType(str, Enum):
    """SSE event types sent during streaming.

    Sent as the ``event:`` field in SSE frames. The frontend's SSE parser
    switches on these values to dispatch to the correct callback.

    Normal flow:   TOKEN* → METADATA → DONE
    With tools:    TOKEN* → (TOOL_CALL_START → TOOL_CALL_END → TOOL_RESULT?)* → TOKEN* → DONE
    Error:         TOKEN* → ERROR
    Abort:         TOKEN* → ABORTED
    """

    TOKEN = "token"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    TOOL_RESULT = "tool_result"
    CITATION = "citation"
    ERROR = "error"
    DONE = "done"
    ABORTED = "aborted"
    METADATA = "metadata"
    RATE_LIMITED = "rate_limited"
    KEEPALIVE = "keepalive"

    # Delegation events — specialist execution surfaced on the main SSE stream.
    DELEGATION_START = "delegation_start"
    DELEGATION_TOKEN = "delegation_token"
    DELEGATION_TOOL_START = "delegation_tool_start"
    DELEGATION_TOOL_DELTA = "delegation_tool_delta"
    DELEGATION_TOOL_END = "delegation_tool_end"
    DELEGATION_TOOL_RESULT = "delegation_tool_result"
    DELEGATION_DONE = "delegation_done"
    DELEGATION_ERROR = "delegation_error"

    # Background-run events — emitted by the app-scoped background run broker.
    BACKGROUND_START = "background_start"
    BACKGROUND_TOKEN = "background_token"
    BACKGROUND_TOOL_START = "background_tool_start"
    BACKGROUND_TOOL_DELTA = "background_tool_delta"
    BACKGROUND_TOOL_END = "background_tool_end"
    BACKGROUND_TOOL_RESULT = "background_tool_result"
    BACKGROUND_DONE = "background_done"
    BACKGROUND_ERROR = "background_error"
    BACKGROUND_ABORTED = "background_aborted"


# ── Tool Calls ───────────────────────────────────────────────────────────────


class ToolCall(BaseModel):
    """A tool/function call made by the assistant."""

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None
    duration_ms: float | None = None  # Time from tool_call_start to tool_result


class ContextSnapshot(BaseModel):
    """Record of exactly what context was sent to the LLM for an assistant message."""

    agent_session_id: str = ""
    agent_id: str = ""
    system_prompt_chars: int = 0
    messages_total: int = 0
    messages_kept: int = 0
    messages_dropped: int = 0
    tokens_used: int = 0
    tokens_budget: int = 0
    max_turns: int | None = None
    user_message: str = ""
    context_messages: list[dict[str, str]] | None = None
    model: str = ""
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class Message(BaseModel):
    """A single conversation message (user or assistant)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: Role
    content: str = ""
    status: MessageStatus = MessageStatus.COMPLETE
    tool_calls: list[ToolCall] = Field(default_factory=list)
    agent_name: str = ""
    context_snapshot: ContextSnapshot | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Agent Threads ────────────────────────────────────────────────────────────


class AgentThread(BaseModel):
    """A per-agent conversation thread within a session."""

    agent_session_id: str = Field(default_factory=lambda: f"ast_{uuid.uuid4().hex[:12]}")
    agent_id: str = ""
    agent_name: str = ""
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BackgroundAgentRun(BaseModel):
    """Durable session-level record for a background agent execution."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    agent_id: str
    source_agent_id: str = ""
    status: AgentRunStatus = AgentRunStatus.QUEUED
    requested_task: str = ""
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


# ── Session base (generic persistence shape — F3 increment 8) ────────────────
#
# The generic half of the session model. A consumer subclasses ``SessionBase``
# to add domain state (GridIQ adds ``scenario_name`` / ``summary_state`` /
# ``priority_action_state`` in ``foundation/models.py``). The base carries only
# the fields the agent-runtime + persistence layer needs: identity, ownership,
# the per-agent message threads, background-run records, optimistic-concurrency
# tag, free-form metadata, and timestamps. Splitting here (not in the consumer)
# lets ``agentkit.persistence`` type its stores against a domain-blind model.


def migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v2 session dict (flat ``messages[]``) to v3 (``threads{}``).

    Called by ``SessionBase``'s ``model_validator`` before pydantic constructs
    the object. Groups flat messages by ``agent_name`` into separate
    ``AgentThread`` entries; messages with empty ``agent_name`` default to the
    ``"orchestrator"`` thread. Pure function — generic (no domain fields are
    read or written; consumer fields such as ``scenario_name`` pass through
    untouched).

    Args:
        data: Raw session dict (from JSON or a persisted document).

    Returns:
        The dict with ``threads`` populated and ``messages`` removed. Returned
        as-is if already v3 or if a ``threads`` key already exists.
    """
    # Already v3 or has threads — no migration needed.
    if data.get("schema_version", 0) >= 3 or "threads" in data:
        return data

    flat_messages = data.pop("messages", [])
    threads: dict[str, dict[str, Any]] = {}
    for msg in flat_messages:
        # ``msg`` may be a raw dict (from JSON) or a pydantic ``Message``
        # (from in-memory cloning). Normalise to dict for uniform access.
        if hasattr(msg, "model_dump"):
            msg = msg.model_dump(mode="json")
        agent_id = msg.get("agent_name", "") or "orchestrator"
        if agent_id not in threads:
            threads[agent_id] = {
                "agent_session_id": f"ast_{uuid.uuid4().hex[:12]}",
                "agent_id": agent_id,
                "agent_name": agent_id,
                "messages": [],
                "created_at": msg.get(
                    "created_at", datetime.now(timezone.utc).isoformat()
                ),
            }
        threads[agent_id]["messages"].append(msg)

    data["threads"] = threads
    data["schema_version"] = 3
    return data


class SessionBase(BaseModel):
    """Generic conversation-session shape (schema v3).

    Domain-blind base for a persisted session. Consumers subclass this to add
    domain state. Carries identity, ownership, per-agent message threads,
    background-run records, an optimistic-concurrency tag, free-form metadata,
    and timestamps. The ``model_validator`` performs the v2→v3 migration so any
    subclass inherits it for free.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str = "New conversation"
    schema_version: int = 3  # v3 = per-agent threads
    user_id: str = (
        ""  # Auth subject id of the session owner. "__default__" = shared.
    )
    threads: dict[str, AgentThread] = Field(default_factory=dict)  # keyed by agent_id
    background_runs: dict[str, BackgroundAgentRun] = Field(default_factory=dict)
    # Free-form server-side metadata bag (diagnostics / self-heal markers).
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Optimistic-concurrency tag. Populated by a durable backend's ``get``
    # (e.g. Cosmos ``_etag``); the in-memory store leaves it ``None``.
    # Excluded from ``model_dump`` so it never crosses the wire or persists.
    etag: str | None = Field(default=None, exclude=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="before")
    @classmethod
    def _migrate_schema(cls, data: Any) -> Any:
        """Auto-migrate v2 sessions (flat ``messages[]``) to v3 (``threads{}``)."""
        if isinstance(data, dict):
            return migrate_v2_to_v3(data)
        return data


class SessionSummaryBase(BaseModel):
    """Generic lightweight session metadata for list views (no messages).

    Consumers subclass to add domain fields (GridIQ adds ``scenario_name``).
    Carries identity, ownership, the four activity counts, and timestamps.
    """

    id: str
    title: str
    user_id: str = ""  # Auth subject id of the session owner.
    message_count: int
    tool_call_count: int = 0  # total tool invocations across all messages
    user_prompt_count: int = 0  # number of user messages
    agent_response_count: int = 0  # number of assistant messages
    created_at: datetime
    updated_at: datetime


# ── SSE wire envelope ────────────────────────────────────────────────────────


class StreamEvent(BaseModel):
    """A single SSE event sent during streaming.

    Wire format: ``event: {type}\\ndata: {json}\\n\\n``.
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
    estimated_cost_usd: float | None = None


__all__ = [
    "Role",
    "MessageStatus",
    "AgentRunStatus",
    "StreamEventType",
    "ToolCall",
    "ContextSnapshot",
    "Message",
    "AgentThread",
    "BackgroundAgentRun",
    "migrate_v2_to_v3",
    "SessionBase",
    "SessionSummaryBase",
    "StreamEvent",
    "StreamMetadata",
]
