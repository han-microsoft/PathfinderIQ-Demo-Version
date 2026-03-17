"""Tests that startup timing instrumentation emits structured logs.

Uses a patched lifespan to capture log records emitted
during startup. Verifies that key timing milestones emit
``startup.*`` log messages with ``duration_ms`` in extra fields.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= python -m pytest tests/unit/test_startup_timing.py -v
"""

import logging
import os

import pytest

from fastapi.testclient import TestClient


@pytest.fixture
def startup_log_records():
    """Capture app.main log records during lifespan startup.

    Attaches a custom handler to the ``app.main`` logger before creating
    a TestClient. Yields captured records + client.
    """
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("OTEL_EXPORT_TARGET", "")

    # Remove COSMOS_SESSION_ENDPOINT to skip Cosmos path
    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

    records: list[logging.LogRecord] = []

    class RecordCapture(logging.Handler):
        """Handler that appends every log record to the shared list."""

        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = RecordCapture()
    main_logger = logging.getLogger("app.main")
    main_logger.addHandler(handler)
    original_level = main_logger.level
    main_logger.setLevel(logging.DEBUG)

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        yield records, client

    main_logger.removeHandler(handler)
    main_logger.setLevel(original_level)
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos


def test_startup_emits_phase1_complete(startup_log_records):
    """Verify lifespan emits startup.phase1_complete with duration_ms."""
    records, _client = startup_log_records

    phase1 = [r for r in records if "startup.phase1_complete" in r.getMessage()]
    assert len(phase1) >= 1, (
        f"Expected startup.phase1_complete log. "
        f"Got messages: {[r.getMessage() for r in records]}"
    )
    # duration_ms is set via extra={} — Python logging stores it as record attr
    assert hasattr(phase1[0], "duration_ms"), "Missing duration_ms on startup.phase1_complete"
    assert phase1[0].duration_ms >= 0, "duration_ms should be non-negative"


def test_startup_emits_session_store_timing(startup_log_records):
    """Verify lifespan emits startup.session_store with duration_ms."""
    records, _client = startup_log_records

    store_logs = [r for r in records if "startup.session_store" in r.getMessage()]
    assert len(store_logs) >= 1, "Expected startup.session_store timing log"
    assert hasattr(store_logs[0], "duration_ms"), "Missing duration_ms"


def test_startup_emits_llm_timing(startup_log_records):
    """Verify lifespan emits startup.llm_service with duration_ms."""
    records, _client = startup_log_records

    llm_logs = [r for r in records if "startup.llm_service" in r.getMessage()]
    assert len(llm_logs) >= 1, "Expected startup.llm_service timing log"
    assert hasattr(llm_logs[0], "duration_ms"), "Missing duration_ms"
