"""Graph explorer tool package — Cosmos DB Gremlin backend.

Exports query_graph from the Cosmos Gremlin implementation (Fabric GQL
backend retired 2026-06-19).
"""

from tools.graph_explorer._cosmos_gremlin import query_graph  # noqa: F401

__all__ = ["query_graph"]
