"""ConversationTurn lifecycle — unit tests.

Tests the ``ConversationTurn`` class from ``app.services.conversation._lifecycle``
using a mock ``SessionStore``. Covers:
    - start() creates user message, auto-titles on first message
    - begin_response() creates placeholder assistant message
    - accumulate_*() builds internal state correctly
    - finalize() with each status (COMPLETE, ERROR, ABORTED)
    - finalize() with tool calls
    - finalize_error() convenience method
    - finalize() without begin_response() (defensive)
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.foundation.models import Message, MessageStatus, Role, Session, ToolCall
from app.services.conversation._lifecycle import ConversationTurn


@pytest.fixture
def mock_store():
    """A mock SessionStore with async methods."""
    store = AsyncMock()
    # append_message, update_message, update, get all return None by default
    store.append_message = AsyncMock()
    store.update_message = AsyncMock()
    store.update = AsyncMock()
    return store


@pytest.fixture
def empty_session():
    """A fresh session with no messages."""
    return Session(title="New conversation", messages=[])


@pytest.fixture
def session_with_messages():
    """A session that already has messages (not first message)."""
    return Session(
        title="Existing title",
        messages=[
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi!"),
        ],
    )


class TestStart:
    """ConversationTurn.start() — user message creation + auto-title."""

    @pytest.mark.asyncio
    async def test_creates_user_message(self, mock_store, empty_session):
        """start() persists a user message via store.append_message."""
        turn = ConversationTurn("sess-1", mock_store)
        msg = await turn.start(empty_session, "Hello world")

        assert msg.role == Role.USER
        assert msg.content == "Hello world"
        mock_store.append_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_titles_on_first_message(self, mock_store, empty_session):
        """First message auto-generates a title from the content."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "Investigate router R-045")

        assert empty_session.title == "Investigate router R-045"
        mock_store.update.assert_called_once_with(empty_session)

    @pytest.mark.asyncio
    async def test_auto_title_truncates_long_message(self, mock_store, empty_session):
        """Messages >50 chars get truncated with ellipsis."""
        long_msg = "A" * 60
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, long_msg)

        assert len(empty_session.title) == 51  # 50 chars + ellipsis
        assert empty_session.title.endswith("\u2026")

    @pytest.mark.asyncio
    async def test_no_auto_title_on_second_message(self, mock_store, session_with_messages):
        """Second+ messages do not change the title."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(session_with_messages, "Another question")

        assert session_with_messages.title == "Existing title"
        mock_store.update.assert_not_called()


class TestBeginResponse:
    """ConversationTurn.begin_response() — placeholder assistant message."""

    @pytest.mark.asyncio
    async def test_creates_streaming_placeholder(self, mock_store, empty_session):
        """begin_response() creates a STREAMING assistant message."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        msg = await turn.begin_response()

        assert msg.role == Role.ASSISTANT
        assert msg.content == ""
        assert msg.status == MessageStatus.STREAMING
        # append_message called twice: user + assistant
        assert mock_store.append_message.call_count == 2


class TestAccumulation:
    """ConversationTurn accumulate_*() methods."""

    @pytest.mark.asyncio
    async def test_accumulate_tokens(self, mock_store, empty_session):
        """Tokens are buffered and joined on finalize."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()

        turn.accumulate_token("Hello")
        turn.accumulate_token(" ")
        turn.accumulate_token("world")

        msg = await turn.finalize(MessageStatus.COMPLETE)
        assert msg.content == "Hello world"

    @pytest.mark.asyncio
    async def test_accumulate_tool_calls(self, mock_store, empty_session):
        """Tool calls are tracked by ID and assembled on finalize."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()

        turn.accumulate_tool_call_start("tc-1", "query_graph")
        turn.accumulate_tool_call_end("tc-1", {"query": "g.V().count()"})
        turn.accumulate_tool_result("tc-1", '{"count": 42}')

        msg = await turn.finalize(MessageStatus.COMPLETE)
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "query_graph"
        assert msg.tool_calls[0].arguments == {"query": "g.V().count()"}
        assert msg.tool_calls[0].result == '{"count": 42}'

    @pytest.mark.asyncio
    async def test_accumulate_unknown_tool_call_id_ignored(self, mock_store, empty_session):
        """Tool call end/result for unknown IDs are silently ignored."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()

        # These should not raise — unknown IDs are ignored
        turn.accumulate_tool_call_end("nonexistent", {"x": 1})
        turn.accumulate_tool_result("nonexistent", "result")

        msg = await turn.finalize(MessageStatus.COMPLETE)
        assert len(msg.tool_calls) == 0


class TestFinalize:
    """ConversationTurn.finalize() — message assembly + persistence."""

    @pytest.mark.asyncio
    async def test_finalize_complete(self, mock_store, empty_session):
        """Finalize with COMPLETE status sets content and persists."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()
        turn.accumulate_token("Answer")

        msg = await turn.finalize(MessageStatus.COMPLETE)

        assert msg.status == MessageStatus.COMPLETE
        assert msg.content == "Answer"
        mock_store.update_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_aborted(self, mock_store, empty_session):
        """Finalize with ABORTED status preserves partial content."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()
        turn.accumulate_token("Partial ")
        turn.accumulate_token("answer")

        msg = await turn.finalize(MessageStatus.ABORTED)

        assert msg.status == MessageStatus.ABORTED
        assert msg.content == "Partial answer"

    @pytest.mark.asyncio
    async def test_finalize_error(self, mock_store, empty_session):
        """finalize_error() sets error text as content."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()
        turn.accumulate_token("some partial")

        msg = await turn.finalize_error("Something went wrong")

        assert msg.status == MessageStatus.ERROR
        assert msg.content == "Something went wrong"

    @pytest.mark.asyncio
    async def test_finalize_empty_content(self, mock_store, empty_session):
        """Finalize with no accumulated tokens → empty content string."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()

        msg = await turn.finalize(MessageStatus.COMPLETE)
        assert msg.content == ""

    @pytest.mark.asyncio
    async def test_finalize_without_begin_response(self, mock_store, empty_session):
        """Finalize without begin_response returns a default message."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        # Skip begin_response — defensive path

        msg = await turn.finalize(MessageStatus.ERROR)
        assert msg.status == MessageStatus.ERROR
        assert msg.role == Role.ASSISTANT


class TestObservability:
    """ConversationTurn structured logging."""

    @pytest.mark.asyncio
    async def test_turn_started_log(self, mock_store, empty_session, caplog):
        """start() emits a 'conversation.turn.started' log."""
        turn = ConversationTurn("sess-1", mock_store)
        with caplog.at_level(logging.INFO):
            await turn.start(empty_session, "Hello")

        started_logs = [r for r in caplog.records if r.message == "conversation.turn.started"]
        assert len(started_logs) == 1
        assert started_logs[0].session_id == "sess-1"
        assert started_logs[0].user_message_length == 5

    @pytest.mark.asyncio
    async def test_turn_completed_log(self, mock_store, empty_session, caplog):
        """finalize() emits a 'conversation.turn.completed' log."""
        turn = ConversationTurn("sess-1", mock_store)
        await turn.start(empty_session, "test")
        await turn.begin_response()
        turn.accumulate_token("Answer")

        with caplog.at_level(logging.INFO):
            await turn.finalize(MessageStatus.COMPLETE)

        completed_logs = [r for r in caplog.records if r.message == "conversation.turn.completed"]
        assert len(completed_logs) == 1
        assert completed_logs[0].status == "complete"
        assert completed_logs[0].content_length == 6
        assert completed_logs[0].tool_call_count == 0
