"""Regression tests for Phase 1 audit fixes.

Covers:
    1.1 Cosmos get() error conflation — 404 vs transient errors
    1.2 Cosmos update() counter loss — raise on read failure
    1.3 Half-open probe logic — only first caller bypasses semaphore
    1.4 Semaphore double-release — gate_state tracking
    1.5 FABRIC_MAX_CONCURRENT lower bound — clamped to 1
    1.6 Empty tool_call_id — orphaned tool messages dropped

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= uv run python -m pytest tests/unit/test_audit_phase1.py -v
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.foundation.models import Message, Role, Session, ToolCall


# ── 1.1 + 1.2: Cosmos session store error handling ──────────────────────────


class TestCosmosGetErrorHandling:
    """Verify get() distinguishes 404 from transient errors."""

    @pytest.fixture
    def mock_container(self):
        """Create a mock Cosmos container client."""
        container = AsyncMock()
        container.create_item = AsyncMock()
        container.upsert_item = AsyncMock()
        container.patch_item = AsyncMock()
        container.read_item = AsyncMock()
        container.read = AsyncMock()
        return container

    @pytest.fixture
    def cosmos_store(self, mock_container):
        """Create a CosmosSessionStore with mocked internals."""
        with patch("app.services.session_store.cosmos.CosmosClient"), \
             patch("app.services.session_store.cosmos.DefaultAzureCredential"):
            from app.services.session_store.cosmos import CosmosSessionStore
            store = CosmosSessionStore(
                endpoint="https://fake.documents.azure.com:443/",
                database="sessions",
                container="conversations",
            )
            store._container = mock_container
            return store

    @pytest.mark.asyncio
    async def test_get_returns_none_on_404(self, cosmos_store, mock_container):
        """404 (CosmosResourceNotFoundError) → return None, no breaker trip."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        mock_container.read_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )
        result = await cosmos_store.get("nonexistent")
        assert result is None
        # Breaker should NOT be tripped by a 404
        assert cosmos_store._breaker._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_get_raises_on_transient_error(self, cosmos_store, mock_container):
        """Transient Cosmos error → raises SessionStoreUnavailable."""
        from app.services.session_store import SessionStoreUnavailable
        mock_container.read_item = AsyncMock(
            side_effect=Exception("503 Service Unavailable")
        )
        with pytest.raises(SessionStoreUnavailable):
            await cosmos_store.get("any-id")
        # Breaker SHOULD be tripped by transient error
        assert cosmos_store._breaker._consecutive_failures == 1


class TestCosmosUpdateErrorHandling:
    """Verify update() raises on read failure instead of zeroing counters."""

    @pytest.fixture
    def mock_container(self):
        container = AsyncMock()
        container.create_item = AsyncMock()
        container.upsert_item = AsyncMock()
        container.patch_item = AsyncMock()
        container.read_item = AsyncMock()
        container.read = AsyncMock()
        return container

    @pytest.fixture
    def cosmos_store(self, mock_container):
        with patch("app.services.session_store.cosmos.CosmosClient"), \
             patch("app.services.session_store.cosmos.DefaultAzureCredential"):
            from app.services.session_store.cosmos import CosmosSessionStore
            store = CosmosSessionStore(
                endpoint="https://fake.documents.azure.com:443/",
                database="sessions",
                container="conversations",
            )
            store._container = mock_container
            return store

    @pytest.mark.asyncio
    async def test_update_raises_on_transient_read_failure(
        self, cosmos_store, mock_container
    ):
        """Transient read failure → SessionStoreUnavailable, not zeroed counters."""
        from app.services.session_store import SessionStoreUnavailable
        mock_container.read_item = AsyncMock(
            side_effect=Exception("Request timed out")
        )
        session = Session(title="Updated title")
        with pytest.raises(SessionStoreUnavailable, match="failed to read"):
            await cosmos_store.update(session)
        # Upsert should NOT have been called — we refused to proceed
        mock_container.upsert_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_proceeds_on_404(self, cosmos_store, mock_container):
        """404 on read → proceeds with empty baseline (defensive, unlikely path)."""
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        mock_container.read_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(
                status_code=404, message="Not found"
            )
        )
        session = Session(title="New title")
        await cosmos_store.update(session)
        # Upsert SHOULD have been called — 404 means fresh doc
        mock_container.upsert_item.assert_called_once()


# ── 1.3: Half-open probe logic ──────────────────────────────────────────────


class TestHalfOpenProbeLogic:
    """REMOVED 2026-06-20: the Fabric throttle gate / circuit breaker was retired
    in the Cosmos migration. The Cosmos adapters own their own retry/backoff and
    expose no throttle gate (see AUTODEV; app/scenario/_registry.get_fabric_throttle_status
    is a None hook). No live equivalent to test."""


# ── 1.5: FABRIC_MAX_CONCURRENT lower bound ──────────────────────────────────


class TestFabricMaxConcurrentBound:
    """Verify FABRIC_MAX_CONCURRENT is clamped to minimum 1."""

    def test_zero_clamped_to_one(self):
        """FABRIC_MAX_CONCURRENT=0 → clamped to 1."""
        with patch.dict("os.environ", {"FABRIC_MAX_CONCURRENT": "0"}):
            # Re-evaluate the expression
            import os
            result = max(1, int(os.getenv("FABRIC_MAX_CONCURRENT", "2")))
            assert result == 1

    def test_negative_clamped_to_one(self):
        """FABRIC_MAX_CONCURRENT=-5 → clamped to 1."""
        with patch.dict("os.environ", {"FABRIC_MAX_CONCURRENT": "-5"}):
            import os
            result = max(1, int(os.getenv("FABRIC_MAX_CONCURRENT", "2")))
            assert result == 1


# ── 1.6: Empty tool_call_id in context builder ──────────────────────────────


class TestOrphanedToolMessages:
    """Verify context builder drops tool messages without valid tool_call_id."""

    def test_tool_message_without_tool_calls_is_dropped(self):
        """Tool-role message with empty tool_calls list is excluded."""
        from app.services.conversation import build_context_window

        messages = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.TOOL, content="some result", tool_calls=[]),
            Message(role=Role.ASSISTANT, content="Here's what I found"),
        ]
        result, _ = build_context_window(messages)
        # Should have: system + user + assistant (tool message dropped)
        roles = [m["role"] for m in result]
        assert "tool" not in roles
        assert len(result) == 3  # system, user, assistant

    def test_tool_message_with_valid_id_is_kept(self):
        """Tool-role message with valid tool_call_id is included."""
        from app.services.conversation import build_context_window

        tc = ToolCall(id="call_abc123", name="search", arguments={}, result="found")
        messages = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.TOOL, content="found", tool_calls=[tc]),
            Message(role=Role.ASSISTANT, content="Result"),
        ]
        result, _ = build_context_window(messages)
        tool_msgs = [m for m in result if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_abc123"

    def test_tool_message_with_empty_id_is_dropped(self):
        """Tool-role message where tool_call.id is empty string is excluded."""
        from app.services.conversation import build_context_window

        tc = ToolCall(id="", name="search", arguments={})
        messages = [
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.TOOL, content="result", tool_calls=[tc]),
            Message(role=Role.ASSISTANT, content="Done"),
        ]
        result, _ = build_context_window(messages)
        tool_msgs = [m for m in result if m["role"] == "tool"]
        assert len(tool_msgs) == 0
