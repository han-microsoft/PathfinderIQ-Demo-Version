"""Tool packages — Cosmos-backed with direct imports.

This file is documentation-only. No imports. The agent loader resolves
tools via importlib from scenario.yaml specs, bypassing this module.

Package layout:
    tools/
    ├── _cosmos.py            — Shared Cosmos adapter wiring (Gremlin + NoSQL seams)
    ├── _spoof_state.py       — Per-session demo state for network/incident tools
    ├── graph_explorer/       — query_graph        (Cosmos DB Gremlin)
    ├── telemetry/            — query_telemetry,    (Cosmos DB NoSQL)
    │                           query_alerts
    ├── search/               — search_runbooks,    (Azure AI Search)
    │                           search_tickets
    ├── capability.py         — find_capabilities  (capability fabric)
    ├── dispatch/             — dispatch_field_engineer  (default)
    ├── workiq/               — ask_work_iq         (spoof)
    ├── math_tools.py         — calculate()
    └── time_tools.py         — get_current_time()

Backend selection:
    All tool packages use direct imports from their single backend
    implementation. No runtime dispatch. The Fabric data-plane stack
    (_fabric_*, GQL/KQL tools) was retired 2026-06-19 in favour of Cosmos.
"""
