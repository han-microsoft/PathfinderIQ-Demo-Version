"""Spoof state module — session-scoped state isolation tests.

Tests that the _spoof_state module correctly isolates state per session,
supports reset operations, and maintains action log ordering.
"""

import pytest

from tools._spoof_state import (
    activate_route,
    get_action_log,
    get_link_status,
    log_action,
    post_advisory,
    reset,
    set_link_status,
)


@pytest.fixture(autouse=True)
def _clear_spoof_state():
    """Reset all spoof state before and after each test."""
    reset()
    yield
    reset()


class TestSessionIsolation:
    """Two sessions must not see each other's spoof state."""

    def test_link_status_isolation(self):
        """Two sessions setting the same link ID get independent state."""
        set_link_status("sess_a", "LINK-1", "admin_down")
        set_link_status("sess_b", "LINK-1", "admin_up")
        assert get_link_status("sess_a", "LINK-1")["status"] == "admin_down"
        assert get_link_status("sess_b", "LINK-1")["status"] == "admin_up"

    def test_action_log_isolation(self):
        """Each session has its own action log."""
        log_action("sess_a", "test_action", detail="alpha")
        log_action("sess_b", "test_action", detail="beta")
        assert len(get_action_log("sess_a")) == 1
        assert len(get_action_log("sess_b")) == 1
        assert get_action_log("sess_a")[0]["detail"] == "alpha"
        assert get_action_log("sess_b")[0]["detail"] == "beta"


class TestReset:
    """Reset clears state correctly."""

    def test_reset_single_session(self):
        """Reset clears only the target session — others preserved."""
        set_link_status("sess_a", "LINK-1", "admin_down")
        set_link_status("sess_b", "LINK-1", "admin_up")
        reset("sess_a")
        assert get_link_status("sess_a", "LINK-1") is None
        assert get_link_status("sess_b", "LINK-1")["status"] == "admin_up"

    def test_reset_all(self):
        """Global reset clears all sessions."""
        set_link_status("sess_a", "LINK-1", "down")
        set_link_status("sess_b", "LINK-2", "up")
        reset()
        assert get_link_status("sess_a", "LINK-1") is None
        assert get_link_status("sess_b", "LINK-2") is None

    def test_reset_is_idempotent(self):
        """Resetting an empty or already-reset session does not error."""
        reset("nonexistent_session")
        reset()


class TestEdgeCases:
    """Edge cases for spoof state lookups."""

    def test_get_link_status_returns_none_for_unknown_session(self):
        """Querying an unknown session returns None, not KeyError."""
        assert get_link_status("nonexistent", "LINK-1") is None

    def test_get_link_status_returns_none_for_unknown_link(self):
        """Querying a known session but unknown link returns None."""
        set_link_status("s1", "LINK-A", "admin_down")
        assert get_link_status("s1", "LINK-B") is None

    def test_set_link_status_overwrites_previous(self):
        """Setting a link status twice overwrites the first value."""
        set_link_status("s1", "LINK-1", "admin_down")
        set_link_status("s1", "LINK-1", "admin_up")
        assert get_link_status("s1", "LINK-1")["status"] == "admin_up"

    def test_action_log_ordering(self):
        """Action log entries are in chronological order."""
        set_link_status("s1", "LINK-1", "down")
        activate_route("s1", "MPLS-BACKUP-02")
        log = get_action_log("s1")
        assert log[0]["action"] == "set_link_status"
        assert log[1]["action"] == "reroute_traffic"


class TestActivateRoute:
    """Route activation state."""

    def test_activate_route_returns_entry(self):
        """activate_route returns entry with is_active, activated_at."""
        entry = activate_route("s1", "MPLS-BACKUP-02", reason="fibre cut")
        assert entry["is_active"] is True
        assert entry["path_id"] == "MPLS-BACKUP-02"
        assert "activated_at" in entry
        assert entry["reason"] == "fibre cut"


class TestPostAdvisory:
    """Advisory posting state."""

    def test_post_advisory_returns_entry(self):
        """post_advisory returns entry with advisory_id, posted_at."""
        entry = post_advisory("s1", "ADV-001", text="Service disruption",
                              regions="Sydney")
        assert entry["advisory_id"] == "ADV-001"
        assert "posted_at" in entry
        assert entry["text"] == "Service disruption"


class TestRequestContextSessionId:
    """RequestContext session_id field."""

    def test_default_session_id_empty(self):
        """RequestContext defaults to empty session_id."""
        from app.foundation.request_context import RequestContext
        ctx = RequestContext()
        assert ctx.session_id == ""

    def test_get_session_id_without_context(self):
        """get_session_id returns empty string when no context set."""
        from app.foundation.request_context import get_session_id
        sid = get_session_id()
        assert sid == ""
