"""Scenario package — single source of truth for scenario data reading.

Fabric-only: no multi-backend resolution, no multi-scenario listing.
"""

# Reader — path resolution, YAML parsing, topology loading
from app.scenario._reader import (  # noqa: F401
    get_scenario_dir,
    get_scenario_file,
    load_scenario_yaml,
    load_topology,
)

# Metadata — display info
from app.scenario._metadata import (  # noqa: F401
    get_scenario_metadata,
    build_scenario_asset_url,
)

# Registry — Fabric backend identity
from app.scenario._registry import (  # noqa: F401
    GRAPH_BACKENDS,
    get_active_backend_id,
    resolve_tool_for_backend,
    get_fabric_throttle_status,
)
