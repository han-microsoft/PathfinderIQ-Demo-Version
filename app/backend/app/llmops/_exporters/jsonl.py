"""JSONL file exporter — append LLM traces to a local .jsonl file.

Module role:
    Simplest TraceExporter implementation. Appends one JSON object per line
    to a local file. Useful for development, debugging, and environments
    where Cosmos DB is not available.

    Uses ``asyncio.to_thread`` for non-blocking file I/O without requiring
    the ``aiofiles`` dependency. Each export opens, appends, and closes the
    file — no persistent file handle to manage.

Key collaborators:
    - ``_protocol.LLMTrace``  — the data model being serialized
    - ``_manager.py``         — calls export() from the background worker

Dependents:
    Created by: ``__init__.configure_llmops()`` when ``LLMOPS_BACKEND=jsonl``
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.llmops._protocol import LLMTrace

logger = logging.getLogger(__name__)

# Maximum JSONL file size before rotation (10 MB).
# Prevents disk exhaustion in containers with limited ephemeral storage.
_MAX_FILE_BYTES = 10 * 1024 * 1024


class JSONLExporter:
    """Append LLM traces to a local JSONL file with size-based rotation.

    Each line is a complete JSON object produced by ``LLMTrace.model_dump_json()``.
    The file is opened in append mode per-write — no persistent handle.

    When the file exceeds ``_MAX_FILE_BYTES``, it is rotated to ``<path>.1``
    (overwriting any previous rotation). This prevents unbounded disk growth
    in containerized environments with limited ephemeral storage.

    Args:
        path: File path for the JSONL output. Created on first write.
    """

    def __init__(self, path: str = "llmops_traces.jsonl") -> None:
        self._path = path

    async def export(self, trace: LLMTrace) -> None:
        """Serialize trace to JSON and append to the JSONL file.

        Runs the synchronous file write in ``asyncio.to_thread`` so the
        event loop is not blocked.

        Args:
            trace: The LLMTrace record to append.
        """
        line = trace.model_dump_json() + "\n"
        await asyncio.to_thread(self._write_sync, line)

    def _write_sync(self, line: str) -> None:
        """Synchronous file append with size-based rotation.

        Opens in append mode each time. Checks file size before writing —
        if it exceeds _MAX_FILE_BYTES, rotates to ``<path>.1`` first.
        """
        # Rotate if file exceeds max size
        try:
            if os.path.exists(self._path) and os.path.getsize(self._path) > _MAX_FILE_BYTES:
                rotated = self._path + ".1"
                os.replace(self._path, rotated)
                logger.info(
                    "llmops.jsonl.rotated",
                    extra={"path": self._path, "rotated_to": rotated},
                )
        except OSError:
            pass  # Race condition or permission error — continue writing
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)

    async def close(self) -> None:
        """No-op — no persistent resources to release."""
        pass
