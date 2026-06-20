"""LLMOps trace data model and exporter Protocol.

``LLMTrace`` is the data unit (one record per LLM invocation): token counts,
cost, duration, tool calls, error info, agent identity, and optional
prompt/completion text. Pydantic ``BaseModel`` for ``model_dump_json()``
consistency.

``TraceExporter`` is the Protocol every export backend implements.

Layer rule:
    pydantic + stdlib only. Domain-blind — no GridIQ vocabulary.

Consumed by:
    - ``agentkit.observability.llmops._manager`` — queues / exports records.
    - ``agentkit.observability.llmops._exporters.jsonl`` — concrete exporter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator


class LLMTrace(BaseModel):
    """One LLM invocation trace — the unit of LLMOps data.

    Captures everything needed for cost analysis, debugging, audit trails,
    and multi-agent observability. Each field has a zero/empty default so
    traces can be created incrementally as data becomes available.

    Attributes:
        trace_id: Correlation ID from the HTTP request (request_id_var).
        session_id: UI session identifier.
        agent_name: Identity of the agent that produced this trace.
            Empty for single-agent; populated per-agent in multi-agent mode.
        model: LLM deployment name (e.g., "gpt-4.1", "gpt-5.4").
        provider: LLM provider key ("agent", "openai", "echo", "mock").
        prompt_tokens: Input tokens consumed.
        completion_tokens: Output tokens generated.
        total_tokens: Sum of prompt + completion tokens.
        duration_ms: Wall-clock milliseconds for the invocation.
        tool_calls: Names of tools invoked during this turn.
        tool_call_count: Number of tool invocations.
        status: Outcome — "complete", "error", "aborted".
        error: Error message if status is "error" (sanitized for storage).
        estimated_cost_usd: Approximate cost from the pricing table.
        prompt_text: Raw prompt text (opt-in, sensitive — None by default).
        completion_text: Raw completion text (opt-in, sensitive — None by default).
        metadata: Arbitrary key-value pairs (user_id, scenario_name, etc.).
    """

    trace_id: str
    session_id: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    agent_name: str = ""
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    tool_calls: list[str] = Field(default_factory=list)
    tool_call_count: int = 0
    status: str = "complete"
    error: str | None = None
    estimated_cost_usd: float | None = None
    prompt_text: str | None = None
    completion_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _warn_sensitive_fields(self):
        """Emit a warning when sensitive prompt/completion text is populated.

        These fields are written to plaintext JSONL files with no encryption
        or access control. Production operators should be aware that enabling
        them persists full conversation content on disk.
        """
        if self.prompt_text or self.completion_text:
            import logging
            logging.getLogger(__name__).warning(
                "llmops.sensitive_fields_populated — prompt_text and/or "
                "completion_text will be exported to plaintext storage. "
                "Ensure data retention and access policies are in place."
            )
        return self


@runtime_checkable
class TraceExporter(Protocol):
    """Interface for LLMOps trace export backends.

    Implementations must be async. The manager calls ``export()`` once per
    trace record and ``close()`` during shutdown.

    Implementations:
        - ``_exporters/jsonl.py``  — append to local JSONL file.
    """

    async def export(self, trace: LLMTrace) -> None:
        """Export a single trace record. Must not raise on transient failures."""
        ...

    async def close(self) -> None:
        """Release resources (file handles, client connections)."""
        ...
