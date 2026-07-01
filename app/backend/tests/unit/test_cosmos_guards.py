"""Read-only guards + limit injection for the live Cosmos tool seams.

Replaces the retired Fabric-era guard tests (GQL/KQL) after the Cosmos
migration. Covers the actual functions wired into the agentkit adapters in
``tools/_cosmos.py``.
"""

import pytest

from tools._cosmos import (
    _validate_gremlin_read_only,
    _transform_gremlin,
    _validate_cosmos_read_only,
    _transform_cosmos,
)
from app.foundation.config import settings


class TestGremlinReadOnlyGuard:
    def test_allows_read_traversal(self):
        assert _validate_gremlin_read_only("g.V().hasLabel('CoreRouter')") is None

    @pytest.mark.parametrize("q", [
        "g.addV('X')",
        "g.V('a').addE('rel').to('b')",
        "g.V('a').drop()",
        "g.V('a').property('k','v')",
    ])
    def test_blocks_writes(self, q):
        assert _validate_gremlin_read_only(q) is not None

    def test_requires_g_prefix(self):
        assert _validate_gremlin_read_only("V().limit(1)") is not None


class TestGremlinLimitInjection:
    def test_injects_limit_when_absent(self):
        out = _transform_gremlin("g.V().hasLabel('X')")
        assert out == f"g.V().hasLabel('X').limit({settings.gremlin_max_results})"

    def test_no_limit_for_aggregates(self):
        assert _transform_gremlin("g.V().count()") == "g.V().count()"

    def test_respects_existing_limit(self):
        assert _transform_gremlin("g.V().limit(5)") == "g.V().limit(5)"


class TestGremlinReservedWordSanitizer:
    """`in` is a reserved word in Cosmos's Groovy Gremlin parser; a bare
    anonymous `in('label')` step throws GraphSyntaxException 'Unexpected token:
    )'. The sanitizer rewrites it to the `__.in(` anonymous traversal form."""

    def test_rewrites_anonymous_in_step(self):
        out = _transform_gremlin(
            "g.V('a').project('x').by(in('amplifies').valueMap(true).fold())"
        )
        assert "__.in('amplifies')" in out
        assert ".by(in(" not in out

    def test_preserves_within_predicate(self):
        # `within(` must not be mangled (lookbehind on word char).
        out = _transform_gremlin("g.V().hasId(within('a','b')).valueMap(true)")
        assert "within('a','b')" in out
        assert "__.in" not in out

    def test_preserves_top_level_in_step(self):
        # A non-anonymous `.in('label')` (lookbehind on `.`) stays intact.
        out = _transform_gremlin("g.V('a').in('governs')")
        assert "g.V('a').in('governs')" in out
        assert "__.in" not in out

    def test_idempotent(self):
        once = _transform_gremlin(
            "g.V('a').project('x').by(in('governs').fold())"
        )
        twice = _transform_gremlin(once)
        assert once == twice

    @pytest.mark.parametrize("word", ["in", "and", "or", "not", "is"])
    def test_rewrites_all_reserved_anonymous_steps(self, word):
        # Every Groovy-reserved anonymous step gets the `__.` prefix.
        out = _transform_gremlin(f"g.V('a').where({word}('x'))")
        assert f"__.{word}('x')" in out
        assert f"where({word}(" not in out

    @pytest.mark.parametrize("word", ["in", "and", "or", "not", "is"])
    def test_preserves_reserved_words_inside_identifiers(self, word):
        # A reserved word embedded in a longer identifier (within, band, axis,
        # cannot, point) must NOT be rewritten (lookbehind on word char).
        embedded = {"in": "within", "and": "band", "or": "color",
                    "not": "cannot", "is": "axis"}[word]
        out = _transform_gremlin(f"g.V().hasId({embedded}('a','b'))")
        assert f"{embedded}('a','b')" in out
        assert "__." not in out


class TestCosmosSqlReadOnlyGuard:
    def test_allows_select(self):
        assert _validate_cosmos_read_only("SELECT * FROM c") is None

    @pytest.mark.parametrize("q", [
        "UPDATE c SET c.x=1",
        "DELETE FROM c",
        "INSERT INTO c VALUES (1)",
        "DROP TABLE c",
    ])
    def test_blocks_writes(self, q):
        assert _validate_cosmos_read_only(q) is not None


class TestCosmosSqlTopInjection:
    def test_injects_top_when_absent(self):
        out = _transform_cosmos("SELECT * FROM c")
        assert out == f"SELECT TOP {settings.cosmos_query_max_rows} * FROM c"

    def test_respects_existing_top(self):
        assert _transform_cosmos("SELECT TOP 3 * FROM c") == "SELECT TOP 3 * FROM c"
