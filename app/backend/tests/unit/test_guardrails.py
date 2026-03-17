"""Query guardrail functions — LIMIT/take injection and read-only validation."""

from tools.graph_explorer._fabric import _ensure_limit, _validate_gql_read_only
from tools.telemetry._fabric import _ensure_take_limit


# ── GQL LIMIT guardrail ─────────────────────────────────────────────────────


class TestGqlEnsureLimit:
    def test_injects_when_missing(self):
        result = _ensure_limit("MATCH (n) RETURN n")
        assert "LIMIT" in result

    def test_preserves_existing(self):
        q = "MATCH (n) RETURN n LIMIT 10"
        assert _ensure_limit(q) == q

    def test_case_insensitive(self):
        q = "MATCH (n) RETURN n limit 5"
        assert _ensure_limit(q) == q


# ── KQL take guardrail ──────────────────────────────────────────────────────


class TestKqlEnsureTake:
    def test_injects_when_missing(self):
        result = _ensure_take_limit("AlertStream")
        assert "| take" in result

    def test_preserves_existing_take(self):
        q = "AlertStream | take 50"
        assert _ensure_take_limit(q) == q

    def test_preserves_existing_top(self):
        q = "AlertStream | top 10 by Timestamp desc"
        assert _ensure_take_limit(q) == q


# ── GQL read-only validation ────────────────────────────────────────────────


class TestGqlReadOnlyValidation:
    def test_allows_match(self):
        assert _validate_gql_read_only("MATCH (n) RETURN n") is None

    def test_blocks_create(self):
        assert _validate_gql_read_only("CREATE (n:Test)") is not None

    def test_blocks_delete(self):
        assert _validate_gql_read_only("DELETE n") is not None

    def test_blocks_set(self):
        assert _validate_gql_read_only("MATCH (n) SET n.x = 1") is not None

    def test_blocks_merge(self):
        assert _validate_gql_read_only("MERGE (n:Test)") is not None

    def test_rejects_too_long(self):
        result = _validate_gql_read_only("x" * 5001)
        assert result is not None
        assert "too long" in result.lower()
