"""Graph explorer tool package — Fabric GQL backend.

Exports query_graph directly from the Fabric implementation.
"""

from tools.graph_explorer._fabric import query_graph  # noqa: F401

__all__ = ["query_graph"]
