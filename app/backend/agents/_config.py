"""Agent configuration — YAML parsing, caching, and iteration.

Module role:
    Reads the ``agents:`` block from the active scenario's ``scenario.yaml``,
    caches it per (scenario, backend) key, and provides iteration/lookup
    functions. This module owns configuration only — no SDK objects, no
    prompt loading, no tool resolution.

Key collaborators:
    - app.foundation.config (settings) — scenario_name, llm_model
    - app.foundation.request_context   — per-request scenario/backend
    - app.scenario                     — get_scenario_dir, load_scenario_yaml

Dependents:
    Imported by: agents/__init__.py (AgentRegistry) only.
"""

from __future__ import annotations

import logging
from typing import Any

from app.foundation.config import settings
from app.scenario import load_scenario_yaml

logger = logging.getLogger(__name__)

# Per-scenario agent config cache. Keyed by scenario_name.
# Bounded to _CACHE_MAX entries to prevent unbounded memory growth.
_agents_config_cache: dict[str, dict[str, Any]] = {}
_CACHE_MAX = 5  # Keep configs for up to 5 scenario/backend combos

# Reserved keys in the agents: block that are NOT agent definitions.
_RESERVED_KEYS = frozenset({"default", "mode"})


def load_agents_block() -> dict[str, Any]:
    """Load and cache the agents block from scenario.yaml.

    Uses a multi-entry cache keyed by (scenario, backend) so concurrent
    users on different scenarios don't invalidate each other's config.
    Bounded to _CACHE_MAX entries — evicts oldest when full.

    Returns:
        The parsed ``agents:`` dict from scenario.yaml.

    Raises:
        ValueError: If scenario.yaml is missing or has no ``agents:`` block.
    """
    # Read from per-request scope (resolved once by middleware)
    from app.foundation.request_scope import get_request_scope

    scope = get_request_scope()
    current_scenario = scope.scenario_name or settings.scenario_name or ""
    cache_key = current_scenario

    # Check cache
    if cache_key in _agents_config_cache:
        return _agents_config_cache[cache_key]

    # Read from scope (already parsed and cached per-request)
    scenario_yaml = scope.scenario_yaml
    if not scenario_yaml:
        # Fall back to direct load (startup, tests without middleware)
        scenario_yaml = load_scenario_yaml()
    if not scenario_yaml:
        raise ValueError(
            f"No scenario.yaml found for scenario '{current_scenario}'. "
            f"Set SCENARIO_NAME in control/.env to a valid scenario folder."
        )

    agents_block = scenario_yaml.get("agents")
    if not agents_block:
        raise ValueError(
            f"scenario.yaml for '{current_scenario}' has no 'agents:' block. "
            f"Add an agents section with a 'default' key and agent definitions."
        )

    # Evict oldest entries if cache is full
    while len(_agents_config_cache) >= _CACHE_MAX:
        oldest_key = next(iter(_agents_config_cache))
        del _agents_config_cache[oldest_key]

    _agents_config_cache[cache_key] = agents_block
    logger.info("Loaded agents config from scenario '%s'", current_scenario)
    return agents_block


def invalidate_cache() -> None:
    """Clear all cached agent configs. Called on scenario switch."""
    _agents_config_cache.clear()
    logger.info("Agent config cache invalidated (all entries cleared)")


def get_default_id(config: dict[str, Any]) -> str:
    """Return the default agent ID from the config block.

    Args:
        config: The parsed ``agents:`` block.

    Returns:
        The value of the ``default`` key, or empty string if absent.
    """
    return config.get("default", "")


def iter_agents(config: dict[str, Any]) -> list[tuple[str, dict]]:
    """Iterate (agent_id, agent_cfg) pairs from the agents block.

    Skips reserved keys (``default``, ``mode``) and non-dict values.

    Args:
        config: The parsed ``agents:`` block from scenario.yaml.

    Returns:
        List of (agent_id, agent_config_dict) tuples.
    """
    entries: list[tuple[str, dict]] = []
    for k, v in config.items():
        if k in _RESERVED_KEYS:
            continue
        if isinstance(v, dict):
            entries.append((k, v))
    return entries


def find_agent(config: dict[str, Any], agent_id: str) -> dict | None:
    """Look up an agent config by ID.

    Args:
        config: The parsed ``agents:`` block.
        agent_id: The agent key to find.

    Returns:
        The agent's config dict, or None if not found.
    """
    for aid, cfg in iter_agents(config):
        if aid == agent_id:
            return cfg
    return None
