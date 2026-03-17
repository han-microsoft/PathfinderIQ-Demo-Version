"""Tool packages — Fabric-only with direct imports.

This file is documentation-only. No imports. The agent loader resolves
tools via importlib from scenario.yaml specs, bypassing this module.

Package layout:
    tools/
    ├── _fabric_auth.py       — Shared Fabric token acquisition
    ├── _fabric_constants.py  — Shared Fabric env vars and tunables
    ├── _fabric_throttle.py   — Shared Fabric semaphore + circuit breaker
    ├── graph_explorer/       — query_graph        (Fabric GQL)
    ├── telemetry/            — query_telemetry     (Fabric KQL)
    ├── search/               — search_runbooks,    (Azure AI Search)
    │                           search_tickets
    ├── dispatch/             — dispatch_field_engineer  (default)
    ├── workiq/               — ask_work_iq         (spoof)
    ├── math_tools.py         — calculate()
    └── time_tools.py         — get_current_time()

Backend selection:
    All tool packages use direct imports from their single backend
    implementation. No runtime dispatch.
"""
