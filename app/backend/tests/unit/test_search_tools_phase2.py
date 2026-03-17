"""Search tool importability and resolution tests for Phase 2.

Tests that the new search_equipment and search_infra_specs tools are
importable via the standard paths and resolvable by agents (AgentRegistry).
"""

from __future__ import annotations


class TestSearchToolImportability:
    """New search tools are importable from the standard package path."""

    def test_search_equipment_importable(self):
        """search_equipment is importable from tools.search package."""
        from tools.search import search_equipment
        assert callable(search_equipment)

    def test_search_infra_specs_importable(self):
        """search_infra_specs is importable from tools.search package."""
        from tools.search import search_infra_specs
        assert callable(search_infra_specs)

    def test_loader_resolves_equipment_tool(self):
        """agents._tools.resolve_tool resolves 'tools.search:search_equipment'."""
        from agents._tools import resolve_tool
        func = resolve_tool("tools.search:search_equipment")
        assert callable(func)

    def test_loader_resolves_infra_specs_tool(self):
        """agents._tools.resolve_tool resolves 'tools.search:search_infra_specs'."""
        from agents._tools import resolve_tool
        func = resolve_tool("tools.search:search_infra_specs")
        assert callable(func)

    def test_search_all_exports(self):
        """tools.search.__all__ includes all four search tools."""
        from tools import search
        assert "search_runbooks" in search.__all__
        assert "search_tickets" in search.__all__
        assert "search_equipment" in search.__all__
        assert "search_infra_specs" in search.__all__
