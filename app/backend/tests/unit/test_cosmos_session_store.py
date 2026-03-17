"""Unit tests for CosmosSessionStore document construction.

Tests the shape of documents written to Cosmos without any real
Cosmos connection. All container methods are AsyncMock instances.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= uv run python -m pytest tests/unit/test_cosmos_session_store.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.foundation.models import Message, Role, Session, ToolCall


@pytest.fixture
def mock_container():
    """Create a mock Cosmos container client."""
    container = AsyncMock()
    container.create_item = AsyncMock()
    container.upsert_item = AsyncMock()
    container.patch_item = AsyncMock()
    container.read_item = AsyncMock()
    container.read = AsyncMock()
    return container


@pytest.fixture
def cosmos_store(mock_container):
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


class TestCreateDocShape:
    """Verify create() produces correct document structure."""

    @pytest.mark.asyncio
    async def test_session_doc_has_all_counter_fields(self, cosmos_store, mock_container):
        """Session doc must include all denormalized counter fields at zero."""
        session = Session(scenario_name="test-scenario", title="Test")
        await cosmos_store.create(session)
        doc = mock_container.create_item.call_args[0][0]
        assert doc["type"] == "session"
        assert doc["message_count"] == 0
        assert doc["tool_call_count"] == 0
        assert doc["thinking_count"] == 0
        assert doc["user_prompt_count"] == 0
        assert doc["agent_response_count"] == 0
        assert doc["scenario_name"] == "test-scenario"

    @pytest.mark.asyncio
    async def test_session_doc_id_matches_session_id(self, cosmos_store, mock_container):
        """Doc id and session_id (partition key) must match Session.id."""
        session = Session(scenario_name="s", title="t")
        await cosmos_store.create(session)
        doc = mock_container.create_item.call_args[0][0]
        assert doc["id"] == session.id
        assert doc["session_id"] == session.id

    @pytest.mark.asyncio
    async def test_session_doc_has_timestamps(self, cosmos_store, mock_container):
        """Created_at and updated_at must be ISO format strings."""
        session = Session(scenario_name="s", title="t")
        await cosmos_store.create(session)
        doc = mock_container.create_item.call_args[0][0]
        assert "created_at" in doc
        assert "updated_at" in doc
        assert isinstance(doc["created_at"], str)


class TestAppendMessage:
    """Verify append_message() doc ID and patch operations."""

    @pytest.mark.asyncio
    async def test_doc_id_uses_message_id(self, cosmos_store, mock_container):
        """Message doc ID must be {session_id}-{message.id} — globally unique."""
        msg = Message(role=Role.USER, content="hello")
        await cosmos_store.append_message("sess-1", msg)
        doc = mock_container.create_item.call_args[0][0]
        assert doc["id"] == f"sess-1-{msg.id}"
        assert doc["message_id"] == msg.id
        assert doc["type"] == "message"

    @pytest.mark.asyncio
    async def test_patch_increments_user_count(self, cosmos_store, mock_container):
        """User message must increment message_count and user_prompt_count."""
        msg = Message(role=Role.USER, content="hello")
        await cosmos_store.append_message("sess-1", msg)
        ops = mock_container.patch_item.call_args[1]["patch_operations"]
        incr_ops = {op["path"]: op["value"] for op in ops if op["op"] == "incr"}
        assert incr_ops["/message_count"] == 1
        assert incr_ops["/user_prompt_count"] == 1

    @pytest.mark.asyncio
    async def test_patch_increments_assistant_count(self, cosmos_store, mock_container):
        """Assistant message must increment agent_response_count, not user_prompt_count."""
        msg = Message(role=Role.ASSISTANT, content="reply")
        await cosmos_store.append_message("sess-1", msg)
        ops = mock_container.patch_item.call_args[1]["patch_operations"]
        incr_ops = {op["path"]: op["value"] for op in ops if op["op"] == "incr"}
        assert incr_ops["/agent_response_count"] == 1
        assert "/user_prompt_count" not in incr_ops

    @pytest.mark.asyncio
    async def test_patch_increments_tool_call_count(self, cosmos_store, mock_container):
        """Tool calls on a message must increment tool_call_count."""
        tc = ToolCall(name="query_graph", arguments={"q": "test"})
        msg = Message(role=Role.ASSISTANT, content="result", tool_calls=[tc])
        await cosmos_store.append_message("sess-1", msg)
        ops = mock_container.patch_item.call_args[1]["patch_operations"]
        incr_ops = {op["path"]: op["value"] for op in ops if op["op"] == "incr"}
        assert incr_ops["/tool_call_count"] == 1

    @pytest.mark.asyncio
    async def test_patch_counts_thinking_tool_calls(self, cosmos_store, mock_container):
        """Thinking tool calls must increment thinking_count separately."""
        tc1 = ToolCall(name="thinking", arguments={})
        tc2 = ToolCall(name="query_graph", arguments={"q": "x"})
        msg = Message(role=Role.ASSISTANT, content="", tool_calls=[tc1, tc2])
        await cosmos_store.append_message("sess-1", msg)
        ops = mock_container.patch_item.call_args[1]["patch_operations"]
        incr_ops = {op["path"]: op["value"] for op in ops if op["op"] == "incr"}
        assert incr_ops["/thinking_count"] == 1
        assert incr_ops["/tool_call_count"] == 2

    @pytest.mark.asyncio
    async def test_patch_sets_updated_at(self, cosmos_store, mock_container):
        """Append must set updated_at on the session doc."""
        msg = Message(role=Role.USER, content="hello")
        await cosmos_store.append_message("sess-1", msg)
        ops = mock_container.patch_item.call_args[1]["patch_operations"]
        set_ops = {op["path"]: op["value"] for op in ops if op["op"] == "set"}
        assert "/updated_at" in set_ops
        assert isinstance(set_ops["/updated_at"], str)


class TestUpdateMessage:
    """Verify update_message() preserves all required fields."""

    @pytest.mark.asyncio
    async def test_upsert_includes_all_fields(self, cosmos_store, mock_container):
        """Upserted message doc must have all fields for a full replace."""
        msg = Message(role=Role.ASSISTANT, content="final answer", tool_calls=[])
        await cosmos_store.update_message("sess-1", msg)
        doc = mock_container.upsert_item.call_args[0][0]
        assert doc["id"] == f"sess-1-{msg.id}"
        assert doc["message_id"] == msg.id
        assert doc["role"] == "assistant"
        assert doc["content"] == "final answer"
        assert doc["type"] == "message"
        assert doc["session_id"] == "sess-1"
        assert "created_at" in doc
        assert "status" in doc

    @pytest.mark.asyncio
    async def test_upsert_serializes_tool_calls(self, cosmos_store, mock_container):
        """Tool calls must be serialized as JSON-safe dicts."""
        tc = ToolCall(name="search", arguments={"q": "test"}, result="found")
        msg = Message(role=Role.ASSISTANT, content="done", tool_calls=[tc])
        await cosmos_store.update_message("sess-1", msg)
        doc = mock_container.upsert_item.call_args[0][0]
        assert len(doc["tool_calls"]) == 1
        assert doc["tool_calls"][0]["name"] == "search"
        assert doc["tool_calls"][0]["result"] == "found"


class TestUserIdInDocs:
    """Verify user_id is written/read correctly in session docs."""

    @pytest.mark.asyncio
    async def test_create_session_includes_user_id_in_doc(
        self, cosmos_store, mock_container
    ):
        """create() must write user_id into the Cosmos session document."""
        session = Session(scenario_name="s", title="t", user_id="oid-123")
        await cosmos_store.create(session)
        doc = mock_container.create_item.call_args[0][0]
        assert doc["user_id"] == "oid-123"

    @pytest.mark.asyncio
    async def test_create_session_default_user_id_empty(
        self, cosmos_store, mock_container
    ):
        """create() with default user_id writes empty string."""
        session = Session(scenario_name="s", title="t")
        await cosmos_store.create(session)
        doc = mock_container.create_item.call_args[0][0]
        assert doc["user_id"] == ""

    @pytest.mark.asyncio
    async def test_list_all_filters_by_user_id(
        self, cosmos_store, mock_container
    ):
        """list_all(user_id='abc') query must filter to user's own sessions only."""
        # Make query_items return an async iterable — we just inspect the query string
        mock_container.query_items = lambda **kwargs: AsyncIterator([])
        await cosmos_store.list_all(user_id="abc")
        # Re-assign so we can capture call args
        captured_queries = []
        original = mock_container.query_items
        def capturing_query_items(**kwargs):
            captured_queries.append(kwargs)
            return AsyncIterator([])
        mock_container.query_items = capturing_query_items
        await cosmos_store.list_all(user_id="abc")
        query = captured_queries[0]["query"]
        assert "c.user_id=@uid" in query
        # __default__ is no longer included — users get cloned copies
        assert "__default__" not in query

    @pytest.mark.asyncio
    async def test_list_all_unfiltered_when_no_user_id(
        self, cosmos_store, mock_container
    ):
        """list_all() without user_id must NOT include user_id filter."""
        captured_queries = []
        def capturing_query_items(**kwargs):
            captured_queries.append(kwargs)
            return AsyncIterator([])
        mock_container.query_items = capturing_query_items
        await cosmos_store.list_all()
        query = captured_queries[0]["query"]
        assert "user_id" not in query

    @pytest.mark.asyncio
    async def test_get_session_includes_user_id(
        self, cosmos_store, mock_container
    ):
        """get() must reconstruct Session with user_id from the doc."""
        mock_container.read_item.return_value = {
            "id": "sess-1",
            "title": "Test",
            "scenario_name": "s",
            "user_id": "oid-999",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        mock_container.query_items = lambda **kwargs: AsyncIterator([])
        session = await cosmos_store.get("sess-1")
        assert session is not None
        assert session.user_id == "oid-999"


class AsyncIterator:
    """Minimal async iterator for mocking query_items return value."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


class TestIsHealthyTimeout:
    """Tests for is_healthy() timeout behavior.

    Verifies that the health check wraps container.read() in a timeout
    so firewalled Cosmos fails fast instead of blocking for 30+ seconds.
    """

    @pytest.mark.asyncio
    async def test_healthy_returns_true_fast(self, cosmos_store):
        """When container.read() succeeds quickly, is_healthy returns True."""
        assert await cosmos_store.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_returns_false(self, cosmos_store, mock_container):
        """When container.read() raises, is_healthy returns False."""
        mock_container.read = AsyncMock(side_effect=Exception("403 Forbidden"))
        assert await cosmos_store.is_healthy() is False

    @pytest.mark.asyncio
    async def test_timeout_returns_false(self, cosmos_store, mock_container):
        """When container.read() exceeds timeout, is_healthy returns False."""
        import asyncio

        async def slow_read(**kwargs):
            """Simulate SDK retrying for 5 seconds behind a firewall."""
            await asyncio.sleep(5)

        mock_container.read = slow_read
        # With a 0.1s timeout, this should fail fast — not block for 5s
        result = await cosmos_store.is_healthy(timeout=0.1)
        assert result is False

    @pytest.mark.asyncio
    async def test_custom_timeout_respected(self, cosmos_store, mock_container):
        """Custom timeout parameter controls the wait_for deadline."""
        import asyncio

        async def medium_read(**kwargs):
            """Takes 0.3s to respond — between the two test thresholds."""
            await asyncio.sleep(0.3)
            return {"id": "test"}

        mock_container.read = medium_read
        # 0.1s timeout → should timeout before 0.3s read completes
        assert await cosmos_store.is_healthy(timeout=0.1) is False
        # 1.0s timeout → should succeed (0.3s < 1.0s)
        assert await cosmos_store.is_healthy(timeout=1.0) is True
