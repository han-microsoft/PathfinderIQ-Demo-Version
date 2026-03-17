"""Telemetry tool package — Fabric KQL backend.

Exports query_telemetry (KQL via Fabric Eventhouse) and
query_alerts (AlertStream events).
"""

from tools.telemetry._fabric import query_telemetry  # noqa: F401
from tools.telemetry._alerts import query_alerts  # noqa: F401

__all__ = ["query_telemetry", "query_alerts"]
