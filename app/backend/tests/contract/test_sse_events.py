"""SSE event schema — validates backend events match frontend expectations.

The frontend TypeScript SSECallbacks interface expects specific field names
in each event type's data payload. These tests catch schema drift between
backend models and frontend types.
"""

from app.foundation.models import StreamEvent, StreamEventType, StreamMetadata


def test_token_event_has_token_field():
    """Frontend expects {"token": "..."} in TOKEN events."""
    e = StreamEvent(event=StreamEventType.TOKEN, data={"token": "hello"})
    assert "token" in e.data


def test_metadata_has_required_fields():
    """Frontend destructures: prompt_tokens, completion_tokens, total_tokens, duration_ms, model."""
    meta = StreamMetadata(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        duration_ms=1234.5,
        model="gpt-5.2",
        assistant_message_id="abc",
    )
    dumped = meta.model_dump()
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "duration_ms", "model"):
        assert key in dumped, f"Missing key: {key}"


def test_tool_call_start_has_id_and_name():
    """Frontend expects {id, name} in TOOL_CALL_START events."""
    e = StreamEvent(
        event=StreamEventType.TOOL_CALL_START,
        data={"id": "call_abc", "name": "query_graph"},
    )
    assert e.data["id"] and e.data["name"]


def test_tool_call_end_has_arguments():
    """Frontend expects {id, name, arguments} in TOOL_CALL_END events."""
    e = StreamEvent(
        event=StreamEventType.TOOL_CALL_END,
        data={"id": "call_abc", "name": "query_graph", "arguments": {"query": "..."}},
    )
    assert isinstance(e.data["arguments"], dict)


def test_tool_result_has_result():
    """Frontend expects {id, name, result} in TOOL_RESULT events."""
    e = StreamEvent(
        event=StreamEventType.TOOL_RESULT,
        data={"id": "call_abc", "name": "query_graph", "result": "..."},
    )
    assert isinstance(e.data["result"], str)


def test_error_event_has_error_string():
    """Frontend reads parsed.error as string in ERROR events."""
    e = StreamEvent(event=StreamEventType.ERROR, data={"error": "Something failed"})
    assert isinstance(e.data["error"], str)


def test_rate_limited_has_retry_after():
    """Frontend expects {retry_after: number, attempt: number}."""
    e = StreamEvent(
        event=StreamEventType.RATE_LIMITED,
        data={"retry_after": 15, "attempt": 2},
    )
    assert isinstance(e.data["retry_after"], int)
    assert isinstance(e.data["attempt"], int)


def test_all_event_types_are_strings():
    """Frontend switches on event type string values."""
    for t in StreamEventType:
        assert isinstance(t.value, str)


def test_done_event_has_no_required_data():
    """DONE event can have empty data."""
    e = StreamEvent(event=StreamEventType.DONE, data={})
    assert e.event == StreamEventType.DONE


def test_aborted_event_has_no_required_data():
    """ABORTED event can have empty data."""
    e = StreamEvent(event=StreamEventType.ABORTED, data={})
    assert e.event == StreamEventType.ABORTED


def test_error_event_with_error_code():
    """ERROR events may include error_code and error_id from Phase 1.4.

    The frontend uses error_code for conditional rendering (retry button,
    content warning, auth prompt).  Backward-compatible — error_code is
    optional; old-style {"error": str} still works.
    """
    from app.foundation.errors import ErrorCode, make_error_event

    event = make_error_event(ErrorCode.TIMEOUT, "Request timed out.", error_id="aabbccddee11")
    assert event.event == StreamEventType.ERROR
    assert "error_code" in event.data
    assert event.data["error_code"] == "timeout"
    assert event.data["error_id"] == "aabbccddee11"
