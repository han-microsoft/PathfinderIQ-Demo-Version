"""TDD tests for llm/agent.py helper functions.

Written BEFORE the helpers exist (Phase 0). Each test class is marked xfail
until Phase 2 extracts the functions from stream_completion(). When
Phase 2 completes, the xfail markers are removed — all tests should pass.

Module-level functions (_is_rate_limit, _extract_user_message, _extract_usage)
are imported directly. @staticmethod tests call via the class name
(AgentFrameworkService._method_name) — no instance created, no Azure
credentials required.

Test structure:
    TestParseRetrySeconds  — runs immediately (function already exists)
    TestIsRateLimit        — xfail until Phase 2 step 2.1
    TestExtractUserMessage — xfail until Phase 2 step 2.2
    TestExtractUsage       — xfail until Phase 2 step 2.3
    TestMapUpdateToEvents  — xfail until Phase 2 step 2.4
    TestInjectOrphanContext — xfail until Phase 2 step 2.5
"""

import pytest
from unittest.mock import MagicMock


# ── _parse_retry_seconds (module-level, exists already) ─────────────────
# These tests run immediately — no xfail. They lock the existing contract
# against accidental changes during refactoring.


class TestParseRetrySeconds:
    """Lock the contract for _parse_retry_seconds before refactoring."""

    def test_standard_pattern(self):
        """'retry after 10 seconds' → 10."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("retry after 10 seconds") == 10

    def test_alternative_pattern(self):
        """'retry in 15 seconds' → 15 (accepts 'in' as well as 'after')."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("retry in 15 seconds") == 15

    def test_bare_seconds(self):
        """'wait 30 seconds please' → 30 (falls through to bare pattern)."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("wait 30 seconds please") == 30

    def test_no_match_returns_default(self):
        """Unrecognised error text returns the default (15)."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("unknown error") == 15

    def test_custom_default(self):
        """Caller-specified default overrides the built-in 15."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("unknown error", default=20) == 20

    def test_clamp_low(self):
        """Values below 5 are clamped to 5."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("retry after 2 seconds") == 5

    def test_clamp_high(self):
        """Values above 60 are clamped to 60."""
        from app.services.llm.agent import _parse_retry_seconds
        assert _parse_retry_seconds("retry after 120 seconds") == 60


# ── _is_rate_limit (module-level, Phase 2 creates this) ─────────────────


class TestIsRateLimit:
    """TDD: _is_rate_limit(exc) → bool.

    Detects rate-limit errors by scanning the lowercased exception string
    for known patterns. Must return True for all known Azure AI Agent
    Service rate-limit error formats and False for unrelated errors.
    """

    def test_429_in_message(self):
        """HTTP 429 status code in error text."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("HTTP 429 Too Many Requests")) is True

    def test_rate_limit_phrase(self):
        """Literal 'rate limit' in error text."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("rate limit exceeded")) is True

    def test_retry_after_phrase(self):
        """'retry after' indicates server-requested backoff."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("retry after 10 seconds")) is True

    def test_throttle_phrase(self):
        """'throttl' catches both 'throttled' and 'throttling'."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("request was throttled")) is True

    def test_token_rate_limit(self):
        """Azure-specific 'token rate limit' variant."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("token rate limit reached")) is True

    def test_generic_error_false(self):
        """Non-rate-limit errors return False."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("connection refused")) is False

    def test_empty_exception_false(self):
        """Empty exception message returns False."""
        from app.services.llm.agent import _is_rate_limit
        assert _is_rate_limit(Exception("")) is False


# ── _extract_user_message (module-level, Phase 2 creates this) ──────────


class TestExtractUserMessage:
    """TDD: _extract_user_message(messages) → str.

    Scans messages in reverse for the last user message. Returns empty
    string if none found. Does not modify the input list.
    """

    def test_standard_messages(self):
        """Returns last user message from a multi-turn conversation."""
        from app.services.llm.agent import _extract_user_message
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "what is 2+2?"},
        ]
        assert _extract_user_message(msgs) == "what is 2+2?"

    def test_no_user_messages(self):
        """Returns empty string when no user messages exist."""
        from app.services.llm.agent import _extract_user_message
        msgs = [{"role": "system", "content": "prompt"}]
        assert _extract_user_message(msgs) == ""

    def test_empty_list(self):
        """Returns empty string for empty message list."""
        from app.services.llm.agent import _extract_user_message
        assert _extract_user_message([]) == ""

    def test_returns_last_user(self):
        """With multiple user messages, returns the last one."""
        from app.services.llm.agent import _extract_user_message
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
        ]
        assert _extract_user_message(msgs) == "second"


# ── _extract_usage (module-level, Phase 2 creates this) ─────────────────


class TestExtractUsage:
    """TDD: _extract_usage(content, usage_dict) → None (mutates usage_dict).

    Extracts token usage from two possible SDK formats: dict-style
    (standard TypedDict path) and object-style (future-proof attribute
    access). Updates the usage dict in-place.
    """

    def test_dict_style_usage(self):
        """Standard SDK path: usage_details is a dict with known keys."""
        from app.services.llm.agent import _extract_usage
        content = MagicMock()
        content.usage_details = {
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
        usage = {"input": 0, "output": 0, "total": 0}
        _extract_usage(content, usage)
        assert usage == {"input": 100, "output": 50, "total": 150}

    def test_dict_missing_fields(self):
        """Empty dict → all zeros (defensive defaults)."""
        from app.services.llm.agent import _extract_usage
        content = MagicMock()
        content.usage_details = {}
        usage = {"input": 0, "output": 0, "total": 0}
        _extract_usage(content, usage)
        assert usage == {"input": 0, "output": 0, "total": 0}

    def test_object_style_usage(self):
        """Future-proof path: usage_details is an object with attributes."""
        from app.services.llm.agent import _extract_usage
        # Build a non-dict object with the expected attributes
        raw = type("UsageObj", (), {
            "input_token_count": 200,
            "output_token_count": 100,
            "total_token_count": 300,
        })()
        content = MagicMock()
        content.usage_details = raw
        usage = {"input": 0, "output": 0, "total": 0}
        _extract_usage(content, usage)
        assert usage == {"input": 200, "output": 100, "total": 300}

    def test_none_usage_details(self):
        """None usage_details (SDK didn't emit usage) → all zeros."""
        from app.services.llm.agent import _extract_usage
        content = MagicMock()
        content.usage_details = None
        usage = {"input": 0, "output": 0, "total": 0}
        _extract_usage(content, usage)
        assert usage == {"input": 0, "output": 0, "total": 0}


# ── _map_update_to_events (@staticmethod, Phase 2 creates this) ─────────


class TestMapUpdateToEvents:
    """TDD: AgentFrameworkService._map_update_to_events(update, usage) → list.

    Converts a single AgentResponseUpdate from the SDK's streaming API into
    a list of StreamEvent objects for the SSE transport. Pure transform —
    no side effects except usage dict mutation for usage content.
    """

    def _make_update(self, text=None, contents=None, author_name=None):
        """Build a mock AgentResponseUpdate with specified fields."""
        update = MagicMock()
        update.text = text
        update.contents = contents
        update.author_name = author_name
        return update

    def _make_content(self, ct, **kwargs):
        """Build a mock content object with type and named fields."""
        c = MagicMock()
        c.type = ct
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_text_token(self):
        """Text update → single TOKEN event."""
        from app.services.llm.agent import AgentFrameworkService
        update = self._make_update(text="Hello")
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert len(events) == 1
        assert events[0].event.value == "token"
        assert events[0].data["token"] == "Hello"

    def test_function_call_content(self):
        """function_call → TOOL_CALL_START + TOOL_CALL_END events."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content(
            "function_call",
            call_id="call_abc",
            name="query_graph",
            arguments={"query": "MATCH (n) RETURN n"},
        )
        update = self._make_update(contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert len(events) == 2
        assert events[0].event.value == "tool_call_start"
        assert events[1].event.value == "tool_call_end"
        assert events[1].data["arguments"] == {"query": "MATCH (n) RETURN n"}

    def test_function_call_string_args_parsed(self):
        """String arguments are JSON-parsed into a dict."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content(
            "function_call",
            call_id="call_abc",
            name="search",
            arguments='{"q": "test"}',
        )
        update = self._make_update(contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert events[1].data["arguments"] == {"q": "test"}

    def test_function_call_invalid_json_args(self):
        """Invalid JSON string arguments fall back to empty dict."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content(
            "function_call",
            call_id="call_abc",
            name="search",
            arguments="not json",
        )
        update = self._make_update(contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert events[1].data["arguments"] == {}

    def test_function_result_content(self):
        """function_result → single TOOL_RESULT event."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content(
            "function_result",
            call_id="call_abc",
            name="query_graph",
            result='{"data": []}',
        )
        update = self._make_update(contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert len(events) == 1
        assert events[0].event.value == "tool_result"

    def test_usage_content_updates_accumulator(self):
        """usage content updates the dict in-place, emits no SSE events."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content("usage")
        content.usage_details = {
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
        update = self._make_update(contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert events == []
        assert usage == {"input": 100, "output": 50, "total": 150}

    def test_no_text_no_contents(self):
        """Update with no text and no contents → empty event list."""
        from app.services.llm.agent import AgentFrameworkService
        update = self._make_update()
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert events == []

    def test_author_name_default(self):
        """None author_name defaults to 'NetworkOpsAgent'."""
        from app.services.llm.agent import AgentFrameworkService
        update = self._make_update(text="hi", author_name=None)
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert events[0].data["agent"] == "NetworkOpsAgent"

    def test_mixed_text_and_tool_call(self):
        """Update with both text and function_call → 3 events."""
        from app.services.llm.agent import AgentFrameworkService
        content = self._make_content(
            "function_call", call_id="c1", name="search",
            arguments={"q": "test"},
        )
        update = self._make_update(text="Let me search", contents=[content])
        usage = {"input": 0, "output": 0, "total": 0}
        events = AgentFrameworkService._map_update_to_events(update, usage)
        assert len(events) == 3  # TOKEN + TOOL_CALL_START + TOOL_CALL_END


# ── _inject_orphan_context (@staticmethod, Phase 2 creates this) ────────


class TestInjectOrphanContext:
    """TDD: AgentFrameworkService._inject_orphan_context(session, msgs, user_msg).

    Detects orphaned sessions (service_session_id is None) and prepends
    prior conversation history as a <prior_conversation> block. Returns
    the user message unchanged when the session has a live thread.
    """

    def test_new_thread_with_prior_injects(self):
        """Orphaned session + prior messages → augmented user message."""
        from app.services.llm.agent import AgentFrameworkService
        session = MagicMock(service_session_id=None)
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "current"},
        ]
        result = AgentFrameworkService._inject_orphan_context(
            session, msgs, "current"
        )
        assert "<prior_conversation>" in result
        assert "current" in result

    def test_existing_thread_unchanged(self):
        """Active thread (service_session_id set) → user message unchanged."""
        from app.services.llm.agent import AgentFrameworkService
        session = MagicMock(service_session_id="thread-123")
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response"},
            {"role": "user", "content": "current"},
        ]
        result = AgentFrameworkService._inject_orphan_context(
            session, msgs, "current"
        )
        assert result == "current"

    def test_new_thread_no_prior_unchanged(self):
        """First message in session (no prior history) → unchanged."""
        from app.services.llm.agent import AgentFrameworkService
        session = MagicMock(service_session_id=None)
        msgs = [{"role": "user", "content": "first"}]
        result = AgentFrameworkService._inject_orphan_context(
            session, msgs, "first"
        )
        assert result == "first"
