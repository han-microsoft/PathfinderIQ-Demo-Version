"""Boot-time config validation — fail-fast with batch errors.

Module role:
    Validates that all required configuration for the active scenario's
    declared backends and services is present at startup. Catches every
    missing key in one batch rather than discovering them at first use.

    Uses the existing GRAPH_BACKENDS metadata (requires_env, requires_scenario)
    from app.scenario._registry — no new file format needed.

Key collaborators:
    - app.scenario._registry   — GRAPH_BACKENDS dict with requires_env/requires_scenario
    - app.foundation.config    — Settings for provider-level validation
    - app/main.py              — calls validate_boot_config() during startup

Dependents:
    Called by: app.main._check_scenario_consistency()
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _dotpath_lookup(cfg: dict, dotpath: str) -> Any:
    """Navigate a nested dict by dot-separated path.

    Args:
        cfg: The nested dict to navigate.
        dotpath: Dot-separated path (e.g., "services.fabric.workspace_id").

    Returns:
        The value at the path, or empty string if any key is missing.
    """
    val: Any = cfg
    for key in dotpath.split("."):
        if isinstance(val, dict):
            val = val.get(key, {})
        else:
            return ""
    # Return "" for empty dicts (missing leaf) to match "not set" semantics
    if val == {}:
        return ""
    return val


def validate_boot_config(scenario_yaml: dict, settings: Any) -> list[str]:
    """Validate all required config for the active scenario at startup.

    Checks:
    1. Active graph backend has its required env vars and scenario.yaml keys
    2. LLM provider=agent has required Azure AI env vars
    3. AI Search endpoint is set but scenario has search_indexes defined
    4. Fabric telemetry config is present when telemetry backend = fabric

    Args:
        scenario_yaml: The parsed scenario.yaml dict for the active scenario.
        settings: The Settings singleton from app.foundation.config.

    Returns:
        List of human-readable error strings. Empty = all checks passed.
    """
    errors: list[str] = []

    if not scenario_yaml:
        # No scenario loaded — skip validation (startup without scenario)
        return errors

    # Import the backend registry for graph backend validation
    from app.scenario._registry import GRAPH_BACKENDS

    # ── 1. Validate active graph backend ─────────────────────────────────
    backends_block = scenario_yaml.get("backends", {})
    active_graph = backends_block.get("graph", "memory")

    if active_graph in GRAPH_BACKENDS:
        meta = GRAPH_BACKENDS[active_graph]

        # Check env var requirements
        for env_var in meta.get("requires_env", []):
            if not os.getenv(env_var):
                errors.append(
                    f"Graph backend '{active_graph}' requires env var "
                    f"'{env_var}' but it is not set."
                )

        # Check scenario.yaml requirements (dot-path lookup)
        for dotpath in meta.get("requires_scenario", []):
            val = _dotpath_lookup(scenario_yaml, dotpath)
            if not val:
                errors.append(
                    f"Graph backend '{active_graph}' requires "
                    f"'{dotpath}' in scenario.yaml but it is not set."
                )

    # ── 2. Validate LLM provider config ──────────────────────────────────
    if settings.llm_provider == "agent":
        if not os.getenv("AZURE_AI_PROJECT_ENDPOINT"):
            errors.append(
                "LLM_PROVIDER=agent requires env var "
                "'AZURE_AI_PROJECT_ENDPOINT'."
            )
        if not os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"):
            errors.append(
                "LLM_PROVIDER=agent requires env var "
                "'AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME'."
            )

    # ── 3. Validate search index config ──────────────────────────────────
    if settings.ai_search_endpoint:
        search_indexes = scenario_yaml.get("data_sources", {}).get("search_indexes", {})
        if not search_indexes:
            errors.append(
                "AI_SEARCH_ENDPOINT is configured but scenario.yaml "
                "has no 'data_sources.search_indexes' block."
            )

    # ── 4. Validate telemetry backend config ─────────────────────────────
    telemetry_backend = backends_block.get("telemetry", "")
    if telemetry_backend == "fabric":
        svc = scenario_yaml.get("services", {}).get("fabric", {})
        if not svc.get("eventhouse_query_uri"):
            errors.append(
                "Telemetry backend 'fabric' requires "
                "'services.fabric.eventhouse_query_uri' in scenario.yaml."
            )
        if not svc.get("kql_db_name"):
            errors.append(
                "Telemetry backend 'fabric' requires "
                "'services.fabric.kql_db_name' in scenario.yaml."
            )

    return errors
