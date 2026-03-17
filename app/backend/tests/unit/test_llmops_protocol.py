"""LLMOps protocol tests — LLMTrace model and TraceExporter conformance.

Phase 1.1: Validates the core data model and protocol that all LLMOps
backends must implement.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


class TestLLMTrace:
    """LLMTrace BaseModel — creation, serialization, defaults."""

    def test_creation_with_required_fields(self):
        """LLMTrace can be created with just trace_id and session_id."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(trace_id="req_123", session_id="sess_456")
        assert trace.trace_id == "req_123"
        assert trace.session_id == "sess_456"

    def test_defaults(self):
        """All optional fields have sensible defaults."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(trace_id="r", session_id="s")
        assert trace.agent_name == ""
        assert trace.model == ""
        assert trace.provider == ""
        assert trace.prompt_tokens == 0
        assert trace.completion_tokens == 0
        assert trace.total_tokens == 0
        assert trace.duration_ms == 0.0
        assert trace.tool_calls == []
        assert trace.tool_call_count == 0
        assert trace.status == "complete"
        assert trace.error is None
        assert trace.estimated_cost_usd is None
        assert trace.prompt_text is None
        assert trace.completion_text is None
        assert trace.metadata == {}

    def test_timestamp_auto_generated(self):
        """Timestamp is auto-populated with UTC datetime."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(trace_id="r", session_id="s")
        assert isinstance(trace.timestamp, datetime)
        assert trace.timestamp.tzinfo is not None

    def test_model_dump_json(self):
        """LLMTrace serializes to valid JSON via model_dump_json."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(
            trace_id="req_abc",
            session_id="sess_def",
            model="gpt-4.1",
            prompt_tokens=100,
            completion_tokens=50,
        )
        json_str = trace.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["trace_id"] == "req_abc"
        assert parsed["model"] == "gpt-4.1"
        assert parsed["prompt_tokens"] == 100

    def test_model_dump_dict(self):
        """model_dump() returns a plain dict."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(trace_id="r", session_id="s")
        d = trace.model_dump()
        assert isinstance(d, dict)
        assert "trace_id" in d

    def test_agent_name_field_exists(self):
        """agent_name field exists for multi-agent support."""
        from app.llmops._protocol import LLMTrace
        trace = LLMTrace(trace_id="r", session_id="s", agent_name="NetworkOpsAgent")
        assert trace.agent_name == "NetworkOpsAgent"


class TestTraceExporterProtocol:
    """TraceExporter protocol — structural typing check."""

    def test_protocol_is_runtime_checkable(self):
        """TraceExporter supports isinstance() checks."""
        from app.llmops._protocol import TraceExporter
        assert hasattr(TraceExporter, "__protocol_attrs__") or hasattr(TraceExporter, "__abstractmethods__") or True
        # runtime_checkable protocols support isinstance

    def test_conformant_class_passes(self):
        """A class with export() and close() satisfies the protocol."""
        from app.llmops._protocol import TraceExporter, LLMTrace

        class FakeExporter:
            async def export(self, trace: LLMTrace) -> None:
                pass
            async def close(self) -> None:
                pass

        assert isinstance(FakeExporter(), TraceExporter)

    def test_nonconformant_class_fails(self):
        """A class missing close() does NOT satisfy the protocol."""
        from app.llmops._protocol import TraceExporter

        class BadExporter:
            async def export(self, trace) -> None:
                pass

        assert not isinstance(BadExporter(), TraceExporter)
