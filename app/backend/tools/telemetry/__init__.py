"""Telemetry tool package — Cosmos DB NoSQL backend.

Exports query_telemetry (link + sensor readings) and query_alerts
(AlertStream events), both over Cosmos DB NoSQL (Fabric Eventhouse KQL
backend retired 2026-06-19).
"""

from tools.telemetry._cosmos import query_telemetry, query_alerts  # noqa: F401

__all__ = ["query_telemetry", "query_alerts"]
