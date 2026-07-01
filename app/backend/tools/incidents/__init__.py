"""Incident management tools — ticket creation and customer advisories.

Package role:
    Exports ``create_incident_ticket`` and ``update_advisory`` tools for
    the orchestrator agent. Both are demo-mode tools that write to the
    session-scoped spoof state module (_spoof_state.py).

Dependents:
    Imported by: ``agents`` (AgentRegistry) (via importlib from scenario.yaml tool specs)
"""

from tools.incidents._create_ticket import create_incident_ticket  # noqa: F401
from tools.incidents._estimate_blast_radius import estimate_blast_radius  # noqa: F401
from tools.incidents._update_advisory import update_advisory  # noqa: F401

__all__ = ["create_incident_ticket", "estimate_blast_radius", "update_advisory"]
