"""Integration tests — CosmosSessionStore against a real Cosmos DB instance.

Skipped when COSMOS_SESSION_ENDPOINT is not set (CI without Cosmos).
Run explicitly with:
    COSMOS_SESSION_ENDPOINT=https://... uv run python -m pytest tests/integration -v -k cosmos
"""

import os

import pytest

from app.foundation.models import Message, Role, Session, ToolCall

# Skip entire module when no Cosmos endpoint is available
cosmos_endpoint = os.environ.get("COSMOS_SESSION_ENDPOINT", "")
pytestmark = pytest.mark.skipif(
    not cosmos_endpoint, reason="No COSMOS_SESSION_ENDPOINT"
)


@pytest.fixture
async def cosmos_store():
    """Create a CosmosSessionStore connected to the real endpoint."""
    from app.services.session_store.cosmos import CosmosSessionStore

    store = CosmosSessionStore(
        endpoint=cosmos_endpoint,
        database="sessions",
        container="conversations",
    )
    yield store
    await store.close()


@pytest.mark.cosmos
class TestCosmosSessionLifecycle:
    """CRUD lifecycle against a real Cosmos DB serverless instance."""

    @pytest.mark.asyncio
    async def test_create_get_delete(self, cosmos_store):
        """Full lifecycle: create → get → verify fields → delete → confirm gone."""
        session = Session(scenario_name="test", title="Cosmos test")
        created = await cosmos_store.create(session)
        assert created.id == session.id

        loaded = await cosmos_store.get(session.id)
        assert loaded is not None
        assert loaded.title == "Cosmos test"
        assert loaded.scenario_name == "test"

        await cosmos_store.delete(session.id)
        assert await cosmos_store.get(session.id) is None

    @pytest.mark.asyncio
    async def test_append_increments_counts(self, cosmos_store):
        """Appending a user message must increment message_count and user_prompt_count."""
        session = Session(scenario_name="test", title="Counts test")
        await cosmos_store.create(session)
        try:
            msg = Message(role=Role.USER, content="hello")
            await cosmos_store.append_message(session.id, msg)

            summaries = await cosmos_store.list_all()
            found = next((s for s in summaries if s.id == session.id), None)
            assert found is not None
            assert found.message_count == 1
            assert found.user_prompt_count == 1
            assert found.agent_response_count == 0
        finally:
            await cosmos_store.delete(session.id)

    @pytest.mark.asyncio
    async def test_update_preserves_counters(self, cosmos_store):
        """Updating session title must not zero the denormalized counters."""
        session = Session(scenario_name="test", title="Original")
        await cosmos_store.create(session)
        try:
            msg = Message(role=Role.USER, content="hi")
            await cosmos_store.append_message(session.id, msg)

            session.title = "Renamed"
            await cosmos_store.update(session)

            summaries = await cosmos_store.list_all()
            found = next((s for s in summaries if s.id == session.id), None)
            assert found is not None
            assert found.title == "Renamed"
            assert found.message_count == 1
        finally:
            await cosmos_store.delete(session.id)

    @pytest.mark.asyncio
    async def test_get_returns_messages_in_order(self, cosmos_store):
        """Messages must come back in created_at chronological order."""
        session = Session(scenario_name="test", title="Ordering")
        await cosmos_store.create(session)
        try:
            m1 = Message(role=Role.USER, content="first")
            m2 = Message(role=Role.ASSISTANT, content="second")
            await cosmos_store.append_message(session.id, m1)
            await cosmos_store.append_message(session.id, m2)

            loaded = await cosmos_store.get(session.id)
            assert loaded is not None
            assert len(loaded.messages) == 2
            assert loaded.messages[0].content == "first"
            assert loaded.messages[1].content == "second"
        finally:
            await cosmos_store.delete(session.id)

    @pytest.mark.asyncio
    async def test_is_healthy(self, cosmos_store):
        """Health check must return True for a reachable Cosmos container."""
        assert await cosmos_store.is_healthy() is True
