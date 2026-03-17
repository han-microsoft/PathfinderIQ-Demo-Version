"""Integration test fixtures — in-process FastAPI with echo LLM.

The ``client`` fixture clears network-dependent startup paths
(Cosmos DB) so tests run instantly without Azure access.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """TestClient with in-memory session store and echo LLM provider.

    Sets LLM_PROVIDER=echo to bypass agent config validation, then
    wires InMemorySessionStore + EchoLLMService onto app.state.

    Clears COSMOS_SESSION_ENDPOINT so the lifespan skips Cosmos health
    checks during startup.
    """
    # Bypass config validation for LLM provider
    os.environ.setdefault("LLM_PROVIDER", "echo")
    os.environ.setdefault("OTEL_EXPORT_TARGET", "")
    # Force auth disabled — overrides any leftover state from auth_enabled_client
    # fixture. Uses explicit set (not setdefault) because the auth_enabled_client
    # fixture sets AUTH_ENABLED=true, and setdefault would not override it.
    os.environ["AUTH_ENABLED"] = "false"

    # Prevent Cosmos DB connection attempts during lifespan startup
    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

    from app.main import app
    from app.services.session_store.memory import InMemorySessionStore
    from app.services.llm import EchoLLMService
    from app.foundation.config import settings as _settings

    # Patch the settings singleton directly — env var alone doesn't affect
    # the already-instantiated Settings object in cross-fixture scenarios.
    _original_auth = _settings.auth_enabled
    _settings.auth_enabled = False

    app.state.store = InMemorySessionStore()
    app.state.llm = EchoLLMService()
    with TestClient(app, raise_server_exceptions=False) as c:
        # Ensure background warmup state is deterministic for tests.
        # The warmup task runs concurrently and may or may not have
        # completed by the time the first test executes.
        app.state.startup_status = "ready"
        yield c

    _settings.auth_enabled = _original_auth
    # Restore COSMOS_SESSION_ENDPOINT if it was set
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos


@pytest.fixture
def auth_enabled_client():
    """TestClient with AUTH_ENABLED=true and NO auth override.

    Requests without a valid Bearer token will be rejected with 401
    by the real get_current_user dependency. Used to verify that
    endpoints are properly protected.
    """
    os.environ["LLM_PROVIDER"] = "echo"
    os.environ["OTEL_EXPORT_TARGET"] = ""
    os.environ["AUTH_ENABLED"] = "true"
    os.environ["AUTH_CLIENT_ID"] = "test-client-id-for-gate-tests"
    os.environ["AUTH_TENANT_ID"] = "common"

    saved_cosmos = os.environ.pop("COSMOS_SESSION_ENDPOINT", None)

    from app.main import app
    from app.services.session_store.memory import InMemorySessionStore
    from app.services.llm import EchoLLMService
    from app.foundation.config import settings as _settings

    # Patch the settings singleton — env vars alone don't affect the
    # already-instantiated Settings object.
    _original_auth = _settings.auth_enabled
    _original_client_id = _settings.auth_client_id
    _settings.auth_enabled = True
    _settings.auth_client_id = "test-client-id-for-gate-tests"

    app.state.store = InMemorySessionStore()
    app.state.llm = EchoLLMService()
    # Do NOT override get_current_user — let real auth reject

    with TestClient(app, raise_server_exceptions=False) as c:
        app.state.startup_status = "ready"
        yield c

    _settings.auth_enabled = _original_auth
    _settings.auth_client_id = _original_client_id
    if saved_cosmos is not None:
        os.environ["COSMOS_SESSION_ENDPOINT"] = saved_cosmos
    os.environ["AUTH_ENABLED"] = "false"


def parse_sse_body(text: str) -> list[dict]:
    """Parse SSE response body into a list of {event, data} dicts."""
    events = []
    for frame in text.split("\n\n"):
        if not frame.strip():
            continue
        event_type = None
        data_lines = []
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_type:
            raw = "\n".join(data_lines)
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"raw": raw}
            events.append({"event": event_type, "data": data})
    return events
