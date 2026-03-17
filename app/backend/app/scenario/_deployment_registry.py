"""Scenario deployment registry reader for runtime scenario readiness.

Module role:
    Reads the local scenario deployment registry written by graph_data publish
    workflows. This module keeps runtime binding resolution inside the backend
    layer without importing provisioning scripts directly.

Current scope:
    - load the local JSON registry from graph_data/runtime/
    - return one scenario record by name
    - expose simple readiness helpers for scenario listing and request scope
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _registry_path() -> Path:
    """Return the local scenario deployment registry path."""
    override = os.environ.get("SCENARIO_DEPLOYMENT_REGISTRY_PATH", "").strip()
    if override:
        return Path(override)

    from app.scenario._reader import _graph_data_root

    return _graph_data_root() / "runtime" / "scenario_deployments.json"


def load_deployment_registry() -> dict[str, Any]:
    """Load the deployment registry, returning an empty registry when absent."""
    registry_path = _registry_path()
    if not registry_path.is_file():
        return {"version": 1, "updated_at": "", "scenarios": {}}
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": "", "scenarios": {}}
    payload.setdefault("version", 1)
    payload.setdefault("updated_at", "")
    payload.setdefault("scenarios", {})
    return payload


def get_scenario_deployment(scenario_name: str | None) -> dict[str, Any]:
    """Return one scenario deployment record from the local registry."""
    if not scenario_name:
        return {}
    payload = load_deployment_registry()
    scenarios = payload.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return {}
    record = scenarios.get(scenario_name, {})
    return record if isinstance(record, dict) else {}


def scenario_is_ready(scenario_name: str | None) -> bool:
    """Return True when the scenario has a ready deployment record."""
    return get_scenario_deployment(scenario_name).get("status") == "ready"