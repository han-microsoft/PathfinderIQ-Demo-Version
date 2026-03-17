"""Contract tests — verify SessionStore protocol conformance.

Both CosmosSessionStore and InMemorySessionStore must implement
all 7 protocol methods with correct signatures. Catches drift
between the protocol and implementations.

Run with:
    LLM_PROVIDER=echo OTEL_EXPORT_TARGET= uv run python -m pytest tests/contract/test_session_contract.py -v
"""

import inspect
from unittest.mock import patch

from app.services.session_store import SessionStore


def _get_protocol_methods() -> set[str]:
    """Extract public method names from the SessionStore protocol."""
    return {
        name
        for name, _ in inspect.getmembers(SessionStore, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


class TestProtocolConformance:
    """Both implementations must have all protocol methods."""

    def test_memory_store_has_all_methods(self):
        """InMemorySessionStore must implement every SessionStore method."""
        from app.services.session_store.memory import InMemorySessionStore
        store = InMemorySessionStore()
        for method in _get_protocol_methods():
            assert hasattr(store, method), f"InMemorySessionStore missing {method}"
            assert callable(getattr(store, method))

    def test_cosmos_store_has_all_methods(self):
        """CosmosSessionStore must implement every SessionStore method."""
        with patch("app.services.session_store.cosmos.CosmosClient"), \
             patch("app.services.session_store.cosmos.DefaultAzureCredential"):
            from app.services.session_store.cosmos import CosmosSessionStore
            store = CosmosSessionStore(
                endpoint="https://fake.documents.azure.com:443/",
                database="sessions",
                container="conversations",
            )
            for method in _get_protocol_methods():
                assert hasattr(store, method), f"CosmosSessionStore missing {method}"
                assert callable(getattr(store, method))

    def test_protocol_has_expected_methods(self):
        """SessionStore protocol must define exactly these methods."""
        expected = {
            "create", "get", "list_all", "update",
            "delete", "append_message", "update_message",
            "get_thread", "create_thread", "get_thread_messages",
        }
        actual = _get_protocol_methods()
        assert actual == expected


class TestSessionModelFields:
    """Verify Session and SessionSummary have user_id field."""

    def test_session_has_user_id_field(self):
        """Session model must have user_id: str with default ''."""
        from app.foundation.models import Session
        s = Session()
        assert hasattr(s, "user_id")
        assert isinstance(s.user_id, str)
        assert s.user_id == ""

    def test_session_summary_has_user_id_field(self):
        """SessionSummary model must have user_id: str."""
        from app.foundation.models import SessionSummary
        ss = SessionSummary(
            id="x", title="t", message_count=0,
            created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01T00:00:00Z",
        )
        assert hasattr(ss, "user_id")
        assert isinstance(ss.user_id, str)

    def test_list_all_accepts_user_id_param(self):
        """InMemorySessionStore.list_all() must accept user_id keyword arg."""
        import inspect
        from app.services.session_store.memory import InMemorySessionStore
        sig = inspect.signature(InMemorySessionStore.list_all)
        assert "user_id" in sig.parameters
