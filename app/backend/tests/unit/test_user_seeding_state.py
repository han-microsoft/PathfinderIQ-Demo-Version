"""Unit tests for UserSeedingState — template tracking and seeding decisions.

Test file role:
    Validates the shared seeding state machine used by both InMemorySessionStore
    and CosmosSessionStore. Tests the decision logic (should_seed), template
    registration (deduplication), and the seeded-user tracking (mark_seeded).
"""

import pytest

from app.services.session_store._user_seeding import UserSeedingState


class TestUserSeedingState:
    """Tests for the UserSeedingState decision logic."""

    def test_initial_state_empty(self):
        """New state has no templates and no seeded users."""
        state = UserSeedingState()
        assert state.template_ids == []
        assert not state.is_seeded("user-1")

    def test_register_template_adds_id(self):
        """register_template adds an ID to the template list."""
        state = UserSeedingState()
        state.register_template("session-abc")
        assert "session-abc" in state.template_ids

    def test_register_template_deduplicates(self):
        """Registering the same ID twice does not create a duplicate."""
        state = UserSeedingState()
        state.register_template("session-abc")
        state.register_template("session-abc")
        assert state.template_ids == ["session-abc"]

    def test_register_template_preserves_order(self):
        """Templates are returned in registration order."""
        state = UserSeedingState()
        state.register_template("s1")
        state.register_template("s2")
        state.register_template("s3")
        assert state.template_ids == ["s1", "s2", "s3"]

    def test_template_ids_returns_copy(self):
        """template_ids property returns a copy, not a mutable reference."""
        state = UserSeedingState()
        state.register_template("s1")
        ids = state.template_ids
        ids.append("mutated")
        assert "mutated" not in state.template_ids

    def test_should_seed_true_for_new_user_with_templates(self):
        """A new user with templates registered should be seeded."""
        state = UserSeedingState()
        state.register_template("s1")
        assert state.should_seed("user-1") is True

    def test_should_seed_false_when_already_seeded(self):
        """should_seed returns False after mark_seeded was called."""
        state = UserSeedingState()
        state.register_template("s1")
        state.mark_seeded("user-1")
        assert state.should_seed("user-1") is False

    def test_should_seed_false_when_no_templates(self):
        """should_seed returns False when no templates are registered."""
        state = UserSeedingState()
        assert state.should_seed("user-1") is False

    def test_should_seed_marks_seeded_when_no_templates(self):
        """When no templates exist, should_seed auto-marks the user seeded."""
        state = UserSeedingState()
        state.should_seed("user-1")
        assert state.is_seeded("user-1")

    def test_mark_seeded_prevents_future_seeding(self):
        """mark_seeded prevents should_seed from returning True again."""
        state = UserSeedingState()
        state.register_template("s1")
        assert state.should_seed("user-1") is True
        state.mark_seeded("user-1")
        assert state.should_seed("user-1") is False

    def test_multiple_users_independent(self):
        """Each user has independent seeding state."""
        state = UserSeedingState()
        state.register_template("s1")
        state.mark_seeded("user-1")
        assert state.should_seed("user-1") is False
        assert state.should_seed("user-2") is True

    def test_reset_clears_all_state(self):
        """reset() clears templates and seeded users."""
        state = UserSeedingState()
        state.register_template("s1")
        state.mark_seeded("user-1")
        state.reset()
        assert state.template_ids == []
        assert not state.is_seeded("user-1")

    def test_is_seeded_false_before_marking(self):
        """is_seeded returns False before any marking."""
        state = UserSeedingState()
        assert state.is_seeded("user-1") is False
