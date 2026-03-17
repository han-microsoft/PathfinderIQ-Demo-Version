"""Network action tools — spoofed MPLS rerouting and link status changes.

Package role:
    Exports ``reroute_traffic`` and ``set_link_status`` tools for the
    orchestrator agent. Both are demo-mode tools that write to the
    session-scoped spoof state module (_spoof_state.py).

Dependents:
    Imported by: ``agents`` (AgentRegistry) (via importlib from scenario.yaml tool specs)
"""

from tools.network._reroute_traffic import reroute_traffic  # noqa: F401
from tools.network._set_link_status import set_link_status  # noqa: F401

__all__ = ["reroute_traffic", "set_link_status"]
