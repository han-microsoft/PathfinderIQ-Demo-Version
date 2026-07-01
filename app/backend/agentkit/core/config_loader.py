"""Agent config loader (K1) — domain-blind YAML loader with injectable paths.

Module role:
    Reads and caches ``agent_config.yaml``. Paths are injectable: the consumer
    either passes ``config_path`` per call, or configures a process-wide default
    control directory once via :func:`set_default_control_dir` (GridIQ's
    composition root / ``agent`` shim does this at import). With no default
    configured and no path passed, the zero-arg helpers fail loud rather than
    guessing a project root — agentkit ships no GridIQ filesystem assumptions.

Layering:
    stdlib + PyYAML only. Imports no GridIQ package (§3.6 of
    genericize/TIER1_EXTRACTION_PLAN.md). Was ``agent/config_loader.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ── Reserved keys in the agents: block that are NOT agent definitions ────────
_RESERVED_KEYS = frozenset({"default", "mode"})

# ── Injectable process-wide defaults (configured by the consumer) ────────────
# The control directory holding ``agent_config.yaml`` and ``prompts/``. The
# generic package ships no hardcoded project root; GridIQ sets this from its
# composition root (see ``agent/_compose.py``).
_default_control_dir: Path | None = None
# Fallback agent id when a config omits the ``default`` key. Empty = no
# fallback (domain-blind); GridIQ sets ``"grid_manager"``.
_default_agent_fallback: str = ""

# ── Module-level caches ──────────────────────────────────────────────────────
_cached_configs: dict[Path, tuple[int, dict[str, Any]]] = {}
_cached_agents_blocks: dict[Path, dict[str, Any]] = {}


def set_default_control_dir(path: Path | str) -> None:
    """Register the process-wide default control directory.

    Idempotent. Called once by the consumer's composition root so the zero-arg
    loaders resolve ``<control>/agent_config.yaml`` and ``<control>/prompts``.
    """
    global _default_control_dir
    _default_control_dir = Path(path).resolve()


def set_default_agent_fallback(agent_id: str) -> None:
    """Register the fallback agent id used when a config omits ``default``."""
    global _default_agent_fallback
    _default_agent_fallback = agent_id or ""


def _control_dir() -> Path:
    """Return the configured default control dir or fail loud."""
    if _default_control_dir is None:
        raise RuntimeError(
            "agentkit.core.config_loader: no default control directory configured. "
            "Call set_default_control_dir(<path>) at composition time, or pass "
            "config_path explicitly."
        )
    return _default_control_dir


def _default_config_path() -> Path:
    """Resolve the default ``agent_config.yaml`` path from the control dir."""
    return _control_dir() / "agent_config.yaml"


def load_agent_config(config_path: Path | None = None) -> dict[str, Any]:
    """Parse an agent config YAML file.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir's ``agent_config.yaml``.

    Returns:
        Parsed YAML dict, or empty dict if not found.
    """
    path = (config_path or _default_config_path()).resolve()
    if not path.exists():
        logger.warning("agent_config.yaml not found at %s", path)
        return {}
    stat = path.stat()
    cached = _cached_configs.get(path)
    if cached and cached[0] == stat.st_mtime_ns:
        return cached[1]
    try:
        with open(path) as f:
            parsed = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        logger.warning("Failed to parse agent_config.yaml: %s", e)
        raise
    if not isinstance(parsed, dict):
        raise ValueError("agent_config.yaml root must be a mapping")
    _cached_configs[path] = (stat.st_mtime_ns, parsed)
    _cached_agents_blocks.pop(path, None)
    return parsed


def get_prompts_dir(config_path: Path | None = None) -> Path:
    """Return the prompts directory path from config.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir.

    Returns:
        Resolved absolute path to the prompts directory.
    """
    # The prompts dir is resolved relative to the control directory that holds
    # the config file: ``<control>/<prompts_dir>``.
    control = config_path.resolve().parent if config_path else _control_dir()
    cfg = load_agent_config(config_path)
    rel = cfg.get("prompts_dir", "prompts")
    return control / rel


def invalidate_config_cache() -> None:
    """Clear both the YAML LRU cache and the agents block cache."""
    from agentkit.core.prompt_loader import invalidate_foundation_prompt_cache

    _cached_configs.clear()
    _cached_agents_blocks.clear()
    invalidate_foundation_prompt_cache()


# Backward-compatible alias used by callers of the old _config.invalidate_cache()
invalidate_cache = invalidate_config_cache


def get_control_dir() -> Path:
    """Return the configured control/ directory.

    Was ``<project_root>/control`` computed from ``__file__`` in GridIQ; now the
    consumer-configured default control dir. Callers that need the directory
    (saved-conversations persistence, request-scope construction) call this.
    """
    return _control_dir()


# ── Typed agent lookup ───────────────────────────────────────────────────────

class AgentNotFound(ValueError):
    """Raised when ``resolve_agent_cfg`` cannot locate an agent ID.

    Subclass of ``ValueError`` so existing ``except ValueError`` handlers keep
    working unchanged.

    Attributes:
        agent_id: The ID that failed to resolve (may be empty if no default).
        available: List of agent IDs present in the config (excludes reserved keys).
    """

    def __init__(self, agent_id: str, available: list[str]):
        self.agent_id = agent_id
        self.available = available
        if not agent_id:
            msg = (
                "No agent_id specified and no 'default' key in agent_config.yaml "
                "agents block."
            )
        else:
            msg = (
                f"Agent '{agent_id}' not found in agent_config.yaml. "
                f"Available agents: {available}"
            )
        super().__init__(msg)


def resolve_agent_cfg(agent_id: str | None) -> tuple[str, dict[str, Any]]:
    """Resolve an agent ID (or default) to ``(target_id, agent_cfg)``.

    Single source of truth for the "load agents block → pick default if none
    specified → look up by id → raise typed error if missing" sequence.

    Raises:
        AgentNotFound: when the resolved id is missing from the config.
    """
    config = load_agents_block()
    target_id = agent_id or get_default_id(config)
    if not target_id:
        raise AgentNotFound("", [aid for aid, _ in iter_agents(config)])

    agent_cfg = find_agent(config, target_id)
    if not isinstance(agent_cfg, dict):
        raise AgentNotFound(target_id, [aid for aid, _ in iter_agents(config)])

    return target_id, agent_cfg


# ── Agents block functions ───────────────────────────────────────────────────

def load_agents_block(config_path: Path | None = None) -> dict[str, Any]:
    """Load and cache the agents block from agent_config.yaml.

    Args:
        config_path: Path to agent_config.yaml. Defaults to the configured
                     control dir.

    Returns:
        The parsed ``agents:`` dict.

    Raises:
        ValueError: If the config is missing or has no ``agents:`` block.
    """
    resolved_path = (config_path or _default_config_path()).resolve()
    if resolved_path in _cached_agents_blocks:
        return _cached_agents_blocks[resolved_path]

    config = load_agent_config(resolved_path)
    if not config:
        raise ValueError(
            "agent_config.yaml not found or empty. "
            "Create control/agent_config.yaml with an agents: block."
        )

    agents_block = config.get("agents")
    if not agents_block:
        raise ValueError(
            "agent_config.yaml has no 'agents:' block. "
            "Add agents with a 'default' key and agent definitions."
        )

    _cached_agents_blocks[resolved_path] = agents_block
    logger.info(
        "Loaded agents config: %d agent(s)",
        len([k for k in agents_block if k not in _RESERVED_KEYS]),
    )
    return agents_block


def get_default_id(config: dict[str, Any]) -> str:
    """Return the default agent ID from the config block.

    Falls back to the configured ``_default_agent_fallback`` (empty for the
    generic package; GridIQ sets ``"grid_manager"``) when the config omits the
    ``default`` key.
    """
    return config.get("default", _default_agent_fallback)


def default_agent_id() -> str:
    """Resolve the default agent identifier from ``agent_config.yaml``.

    Returns:
        Configured default agent id, or the registered fallback when the config
        is missing, malformed, or has no usable default.
    """
    try:
        config = load_agent_config()
    except Exception:
        return _default_agent_fallback
    agents_block = (config or {}).get("agents") or {}
    candidate = agents_block.get("default")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return _default_agent_fallback


def iter_agents(config: dict[str, Any]):
    """Iterate over (agent_id, agent_config) pairs, skipping reserved keys."""
    for key, value in config.items():
        if key not in _RESERVED_KEYS and isinstance(value, dict):
            yield key, value


def find_agent(config: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    """Look up a specific agent's config by ID."""
    if agent_id in _RESERVED_KEYS:
        return None
    return config.get(agent_id)


def get_tool_display_names(config_path: Path | None = None) -> dict[str, str]:
    """Return the tool_display_names mapping from agent_config.yaml.

    Maps tool function names (e.g. 'get_nodes') to human-readable labels
    (e.g. 'Find Grid Assets') for display in a chat UI.

    Returns:
        Dict mapping function name → readable display name. Empty dict if the
        section is not present.
    """
    cfg = load_agent_config(config_path)
    names = cfg.get("tool_display_names", {})
    if not isinstance(names, dict):
        return {}
    return {str(k): str(v) for k, v in names.items()}
