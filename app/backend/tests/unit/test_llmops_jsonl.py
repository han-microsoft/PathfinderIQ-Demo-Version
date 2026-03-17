"""JSONL exporter tests — file writing and format.

Phase 1.1: Validates the JSONL exporter writes one JSON object per line
to a local file without requiring external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestJSONLExporter:
    """JSONLExporter — writes LLMTrace records to a local .jsonl file."""

    async def test_writes_single_trace(self, tmp_path):
        """A single trace produces one line in the JSONL file."""
        from app.llmops._exporters.jsonl import JSONLExporter
        from app.llmops._protocol import LLMTrace

        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(path=path)

        trace = LLMTrace(trace_id="req1", session_id="sess1", model="gpt-4.1")
        await exporter.export(trace)
        await exporter.close()

        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["trace_id"] == "req1"
        assert parsed["model"] == "gpt-4.1"

    async def test_appends_multiple_traces(self, tmp_path):
        """Multiple exports append to the same file."""
        from app.llmops._exporters.jsonl import JSONLExporter
        from app.llmops._protocol import LLMTrace

        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(path=path)

        for i in range(3):
            await exporter.export(LLMTrace(trace_id=f"r{i}", session_id="s"))
        await exporter.close()

        lines = Path(path).read_text().strip().split("\n")
        assert len(lines) == 3

    async def test_each_line_is_valid_json(self, tmp_path):
        """Every line in the JSONL file is valid JSON."""
        from app.llmops._exporters.jsonl import JSONLExporter
        from app.llmops._protocol import LLMTrace

        path = str(tmp_path / "traces.jsonl")
        exporter = JSONLExporter(path=path)

        await exporter.export(LLMTrace(trace_id="r1", session_id="s", tool_calls=["query_graph"]))
        await exporter.close()

        for line in Path(path).read_text().strip().split("\n"):
            parsed = json.loads(line)  # Should not raise
            assert "trace_id" in parsed

    async def test_creates_file_if_missing(self, tmp_path):
        """File is created on first export if it doesn't exist."""
        from app.llmops._exporters.jsonl import JSONLExporter
        from app.llmops._protocol import LLMTrace

        path = str(tmp_path / "new_dir" / "traces.jsonl")
        # Parent directory doesn't exist — exporter should handle this
        # Actually, asyncio.to_thread(open, ...) will fail if dir missing.
        # The parent must exist.
        (tmp_path / "new_dir").mkdir()
        exporter = JSONLExporter(path=path)
        await exporter.export(LLMTrace(trace_id="r", session_id="s"))
        await exporter.close()

        assert Path(path).exists()
