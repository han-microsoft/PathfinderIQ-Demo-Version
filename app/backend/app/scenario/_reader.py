"""Scenario data reader — path resolution, YAML parsing, topology loading.

Module role:
    Single source of truth for scenario filesystem operations. Consolidates
    the previously duplicated scenario reading logic into
one canonical location at Layer 1.

    Provides five core functions:
      1. ``_graph_data_root()``        — locate the graph_data/ directory
      2. ``get_scenario_dir()``        — resolve a scenario folder path
      3. ``load_scenario_yaml()``      — parse a scenario's YAML manifest
      4. ``get_scenario_backends()``   — extract the backends block from YAML
      5. ``load_topology()``           — load topology.json for graph viz

    All functions use per-request context (``get_scenario_name()``) with
    ``settings.scenario_name`` fallback. Path traversal guards prevent
    directory escape attacks.

Layer: 1 (imports only from Layer 0: foundation)
    - app.foundation.config (settings)
    - app.foundation.request_context (get_scenario_name)

Dependents:
Called by: app.scenario._metadata,
    agents (AgentRegistry), routers, tools
"""

from __future__ import annotations

import functools
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from app.foundation.config import settings

logger = logging.getLogger(__name__)


def _get_scenario_name_from_scope() -> str:
    """Read scenario name from RequestScope, falling back to env var."""
    from app.foundation.request_scope import get_request_scope
    return get_request_scope().scenario_name


def _graph_data_root() -> Path:
    """Return the graph_data root directory.

    Priority:
      1. settings.graph_data_dir (explicit override)
      2. Auto-detect: walk up from this file to repo root / graph_data.
         This file is at app/backend/app/scenario/_reader.py.
         Repo root is 4 parents up → graph_data sits beside app/.

    Returns:
        Absolute Path to the graph_data/ directory.
    """
    if settings.graph_data_dir:
        return Path(settings.graph_data_dir)
    # app/backend/app/scenario/_reader.py → parents[4] = repo root
    return Path(__file__).resolve().parents[4] / "graph_data"


def get_scenario_dir(scenario_name: str | None = None) -> Path | None:
    """Return the absolute path to a scenario folder, or None.

    Args:
        scenario_name: Explicit scenario name. If None, reads from per-request
            context (X-Scenario-Name header) with settings.scenario_name fallback.

    Returns:
        Path to scenario directory, or None if not found or blocked.

    Side effects:
        Logs ERROR on path traversal attempt. Logs WARNING if dir not found.
    """
    if scenario_name is None:
        scenario_name = _get_scenario_name_from_scope() or settings.scenario_name
    if not scenario_name:
        return None
    # Path traversal guard — scenario_name must not contain path separators
    # or parent-directory references to prevent directory escape.
    if any(c in scenario_name for c in ("../", "..\\", "/", "\\", "\x00")):
        logger.error(
            "scenario.path_traversal_blocked",
            extra={"scenario_name": scenario_name},
        )
        return None
    d = _graph_data_root() / "data" / "scenarios" / scenario_name
    if d.is_dir():
        return d
    logger.warning("Scenario dir not found: %s", d)
    return None


@functools.lru_cache(maxsize=8)
def _load_scenario_yaml_cached(scenario_name: str) -> dict[str, Any]:
    """Parse + cache scenario.yaml keyed by the RESOLVED scenario name.

    Keying by resolved name (never the raw ``None`` argument) prevents a
    no-scope startup call from poisoning the cache with an empty dict that
    would then be returned for every scenario — a latent swap bug.
    """
    if not scenario_name:
        return {}
    scenario_dir = get_scenario_dir(scenario_name)
    if not scenario_dir:
        return {}
    yaml_path = scenario_dir / "scenario.yaml"
    if not yaml_path.exists():
        return {}
    try:
        with open(yaml_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to parse scenario.yaml: %s", e)
        return {}


def load_scenario_yaml(scenario_name: str | None = None) -> dict[str, Any]:
    """Parse scenario.yaml for the active (or specified) scenario.

    Args:
        scenario_name: Explicit name. If None, uses per-request context
            with settings.scenario_name fallback.

    Returns:
        Parsed YAML dict, or empty dict if not found or unparseable.
    """
    if scenario_name is None:
        scenario_name = _get_scenario_name_from_scope() or settings.scenario_name
    return _load_scenario_yaml_cached(scenario_name or "")


def get_scenario_file(
    relative_path: str | None,
    scenario_name: str | None = None,
) -> Path | None:
    """Resolve a scenario-relative file path with traversal protection.

    Args:
        relative_path: Path relative to the scenario root directory.
        scenario_name: Explicit scenario name. If None, uses per-request context.

    Returns:
        Absolute Path to the file when it exists inside the scenario directory.
        Returns None when the path is missing, invalid, escapes the scenario
        root, or points to a non-file entry.

    Side effects:
        Logs WARNING for missing files and ERROR for directory traversal
        attempts so asset-loading failures are traceable during scenario authoring.
    """
    if not relative_path:
        return None

    scenario_dir = get_scenario_dir(scenario_name)
    if not scenario_dir:
        return None

    scenario_root = scenario_dir.resolve()
    candidate = (scenario_root / relative_path).resolve()
    try:
        candidate.relative_to(scenario_root)
    except ValueError:
        logger.error(
            "scenario.file_path_traversal_blocked",
            extra={
                "scenario_name": scenario_name or _get_scenario_name_from_scope(),
                "relative_path": relative_path,
            },
        )
        return None

    if not candidate.is_file():
        logger.warning(
            "scenario.file_not_found",
            extra={
                "scenario_name": scenario_name or _get_scenario_name_from_scope(),
                "relative_path": relative_path,
            },
        )
        return None

    return candidate


def load_topology(scenario_name: str | None = None) -> dict[str, Any]:
    """Load topology.json from a scenario folder.

    Args:
        scenario_name: Explicit name. If None, uses per-request context.

    Returns:
        Dict with ``topology_nodes`` and ``topology_edges`` keys.
        Empty lists if file not found or parse error.
    """
    scenario_dir = get_scenario_dir(scenario_name)
    if not scenario_dir:
        return {"topology_nodes": [], "topology_edges": []}

    topo_path = scenario_dir / "topology.json"
    if not topo_path.exists():
        return {"topology_nodes": [], "topology_edges": []}

    try:
        with open(topo_path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to parse topology.json: %s", e)
        return {"topology_nodes": [], "topology_edges": []}
