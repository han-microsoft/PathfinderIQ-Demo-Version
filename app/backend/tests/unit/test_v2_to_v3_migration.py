"""Tests for migrate_v2_to_v3: flat messages[] → per-agent threads{}.

Covers:
    - Already v3 data passes through unchanged
    - Data with threads key skips migration
    - v2 messages grouped by agent_name into threads
    - Empty agent_name defaults to "orchestrator"
    - Mixed agent_names create separate threads
    - Empty messages list produces empty threads
    - schema_version updated to 3 after migration
"""

import pytest

from app.foundation.models import migrate_v2_to_v3


class TestMigrateV2ToV3:
    """migrate_v2_to_v3: pure function converting flat messages to threads."""

    def test_v3_data_passes_through(self):
        """Data with schema_version >= 3 is returned unmodified."""
        data = {"schema_version": 3, "threads": {"orch": {"messages": []}}}
        result = migrate_v2_to_v3(data)
        assert result is data
        assert result["schema_version"] == 3

    def test_data_with_threads_key_skips(self):
        """Presence of 'threads' key skips migration regardless of version."""
        data = {"schema_version": 1, "threads": {}}
        result = migrate_v2_to_v3(data)
        assert "messages" not in result

    def test_groups_by_agent_name(self):
        """Messages with the same agent_name end up in the same thread."""
        data = {
            "schema_version": 2,
            "messages": [
                {"role": "user", "content": "q1", "agent_name": "net_inv"},
                {"role": "assistant", "content": "a1", "agent_name": "net_inv"},
            ],
        }
        result = migrate_v2_to_v3(data)
        assert "net_inv" in result["threads"]
        assert len(result["threads"]["net_inv"]["messages"]) == 2

    def test_empty_agent_name_defaults_to_orchestrator(self):
        """Messages with empty or missing agent_name go to 'orchestrator'."""
        data = {
            "schema_version": 2,
            "messages": [
                {"role": "user", "content": "hello", "agent_name": ""},
                {"role": "user", "content": "world"},
            ],
        }
        result = migrate_v2_to_v3(data)
        assert "orchestrator" in result["threads"]
        assert len(result["threads"]["orchestrator"]["messages"]) == 2

    def test_mixed_agents_create_separate_threads(self):
        """Different agent_names produce distinct thread entries."""
        data = {
            "schema_version": 2,
            "messages": [
                {"role": "user", "content": "q", "agent_name": "orchestrator"},
                {"role": "assistant", "content": "a", "agent_name": "orchestrator"},
                {"role": "user", "content": "q2", "agent_name": "analyzer"},
                {"role": "assistant", "content": "a2", "agent_name": "analyzer"},
            ],
        }
        result = migrate_v2_to_v3(data)
        assert len(result["threads"]) == 2
        assert "orchestrator" in result["threads"]
        assert "analyzer" in result["threads"]

    def test_empty_messages_produces_empty_threads(self):
        """v2 session with no messages yields empty threads dict."""
        data = {"schema_version": 1, "messages": []}
        result = migrate_v2_to_v3(data)
        assert result["threads"] == {}
        assert result["schema_version"] == 3

    def test_schema_version_set_to_3(self):
        """schema_version is always set to 3 after migration."""
        data = {
            "schema_version": 1,
            "messages": [{"role": "user", "content": "hi", "agent_name": "orch"}],
        }
        result = migrate_v2_to_v3(data)
        assert result["schema_version"] == 3

    def test_messages_key_removed(self):
        """The flat 'messages' key is removed after migration."""
        data = {
            "schema_version": 2,
            "messages": [{"role": "user", "content": "x", "agent_name": "a"}],
        }
        result = migrate_v2_to_v3(data)
        assert "messages" not in result

    def test_thread_has_agent_session_id(self):
        """Each migrated thread gets an agent_session_id starting with 'ast_'."""
        data = {
            "schema_version": 2,
            "messages": [{"role": "user", "content": "hi", "agent_name": "orch"}],
        }
        result = migrate_v2_to_v3(data)
        thread = result["threads"]["orch"]
        assert thread["agent_session_id"].startswith("ast_")
