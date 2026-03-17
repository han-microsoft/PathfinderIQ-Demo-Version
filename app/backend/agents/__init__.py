"""Agent registry — single entry point for all agent operations.

Package role:
    Concentrated authority for agent config, building, and metadata.
    All agent-related operations go through ``AgentRegistry``. The package
    owns: YAML config parsing (_config), prompt loading (_prompts),
    tool resolution (_tools), and SDK agent construction (_builder).

Module layout:
    __init__.py  — AgentRegistry class (this file)
    _config.py   — YAML parsing, caching, iteration
    _builder.py  — SDK agent construction from config dict
    _prompts.py  — Prompt file loading + concatenation
    _tools.py    — importlib tool resolution

Usage:
    from agents import registry

    agent = registry.build("fieldCoordinator", client)
    defs = registry.list_definitions()
    agent_id, name, prompt = registry.get_prompt("fieldCoordinator")
    registry.invalidate()  # on scenario switch
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.scenario import build_scenario_asset_url

from agents._config import (
    load_agents_block,
    invalidate_cache,
    get_default_id,
    iter_agents,
    find_agent,
)
from agents._builder import build_agent
from agents._prompts import load_instructions

logger = logging.getLogger(__name__)


def _extract_agent_ui_metadata(agent_cfg: dict[str, Any]) -> dict[str, Any]:
    """Project optional scenario-owned UI metadata into API-safe fields.

    Args:
        agent_cfg: Raw agent definition from ``scenario.yaml``.

    Returns:
        Dict containing resolved asset URLs and optional product metadata.
    """
    ui_block = agent_cfg.get("ui", {}) if isinstance(agent_cfg.get("ui"), dict) else {}

    powered_by_entries: list[dict[str, str]] = []
    for entry in ui_block.get("powered_by", []) if isinstance(ui_block.get("powered_by"), list) else []:
        if not isinstance(entry, dict):
            continue
        logo_url = build_scenario_asset_url(entry.get("logo"))
        label = str(entry.get("label", "")).strip()
        if not logo_url or not label:
            continue
        powered_by_entries.append({
            "logo_url": logo_url,
            "label": label,
            "description": str(entry.get("description", "")).strip(),
        })

    return {
        "headshot_url": build_scenario_asset_url(ui_block.get("headshot")),
        "full_body_url": build_scenario_asset_url(ui_block.get("full_body")),
        "product_summary": str(ui_block.get("product_summary", "")).strip() or None,
        "powered_by": powered_by_entries,
    }


class AgentRegistry:
    """Concentrated authority for agent config, building, and metadata.

    All callers interact with this class. Delegates to _config, _builder,
    _prompts, and _tools submodules.

    Per-agent client isolation:
        Each agent gets its own AzureAIAgentClient instance to prevent
        identity bleed. The SDK client holds mutable state (agent_name,
        agent_id, _agent_definition) that persists across as_agent() calls.
        Sharing a single client between agents causes whichever agent runs
        first to stamp its identity on the client permanently.

        Call ``configure(client_factory)`` at startup to provide a factory
        function that creates fresh client instances. The registry caches
        one client per agent_id for the process lifetime.
    """

    def __init__(self) -> None:
        """Initialize the registry with empty client cache."""
        # Factory function: () → AzureAIAgentClient. Set by configure().
        self._client_factory: Any | None = None
        # Per-agent client cache: agent_id → AzureAIAgentClient instance.
        # Each agent gets its own client to prevent SDK-level state bleed.
        self._clients: dict[str, Any] = {}

    def configure(self, client_factory: Any) -> None:
        """Register the client factory. Called once at startup.

        Args:
            client_factory: A zero-arg callable that returns a fresh
                AzureAIAgentClient instance. Called once per agent_id.
        """
        self._client_factory = client_factory
        self._clients.clear()  # Reset cache on reconfigure
        logger.info("AgentRegistry configured with client factory")

    def _get_client(self, agent_id: str) -> Any:
        """Get or create a dedicated client for an agent.

        Each agent_id gets its own AzureAIAgentClient instance. The client
        is created on first use and cached for the process lifetime.

        Args:
            agent_id: The agent config key.

        Returns:
            An AzureAIAgentClient instance dedicated to this agent.

        Raises:
            RuntimeError: If configure() has not been called.
        """
        if agent_id in self._clients:
            return self._clients[agent_id]

        if self._client_factory is None:
            raise RuntimeError(
                "AgentRegistry not configured — call registry.configure(client_factory) "
                "at startup. Is LLM_PROVIDER=agent?"
            )

        client = self._client_factory()
        self._clients[agent_id] = client
        logger.info("Created dedicated client for agent '%s'", agent_id)
        return client

    def build(
        self,
        agent_id: str | None,
        client: Any = None,
        *,
        model_override: str = "",
        middleware: Any | None = None,
        context_providers: Any | None = None,
    ) -> Any:
        """Build an SDK Agent by ID from the active scenario's config.

        Uses a dedicated per-agent client to prevent identity bleed.
        If ``client`` is explicitly passed, it is used directly (for
        backward compatibility and testing). Otherwise, the per-agent
        client from the internal cache is used.

        Args:
            agent_id: Config key of the agent to build. None = use default.
            client: An AzureAIAgentClient (or compatible) instance.
            model_override: Explicit model override from retry/fallback loop.
            middleware: Optional SDK middleware instances.
            context_providers: Optional BaseContextProvider instances.

        Returns:
            An Agent object.

        Raises:
            ValueError: If scenario.yaml is missing, malformed, or the
                requested agent_id does not exist.
        """
        from app.scenario import get_scenario_dir

        config = load_agents_block()

        scenario_dir = get_scenario_dir()
        if not scenario_dir:
            from app.foundation.config import settings
            raise ValueError(
                f"Scenario directory not found for '{settings.scenario_name}'. "
                f"Check SCENARIO_NAME in control/.env."
            )
        prompts_dir = scenario_dir / "data" / "prompts"

        target_id = agent_id or get_default_id(config)
        if not target_id:
            raise ValueError(
                "No agent_id specified and no 'default' key in scenario.yaml agents block."
            )

        agent_cfg = find_agent(config, target_id)
        if agent_cfg is None:
            available = [aid for aid, _ in iter_agents(config)]
            raise ValueError(
                f"Agent '{target_id}' not found in scenario.yaml. "
                f"Available agents: {available}"
            )

        # Use the per-agent dedicated client (prevents identity bleed).
        # If a client was explicitly passed (tests, backward-compat), use it.
        effective_client = client if client is not None else self._get_client(target_id)

        return build_agent(
            target_id, agent_cfg, prompts_dir, None, effective_client,
            model_override=model_override,
            middleware=middleware, context_providers=context_providers,
        )

    def get_prompt(self, agent_id: str | None = None) -> tuple[str, str, str]:
        """Load the assembled prompt text for an agent without building an SDK agent.

        Args:
            agent_id: Config key of the agent. None = use default.

        Returns:
            (agent_id, display_name, prompt_text).

        Raises:
            ValueError: If the agent_id is not found.
        """
        from app.scenario import get_scenario_dir

        config = load_agents_block()
        target_id = agent_id or get_default_id(config)
        if not target_id:
            raise ValueError(
                "No agent_id specified and no 'default' key in scenario.yaml agents block."
            )

        agent_cfg = find_agent(config, target_id)
        if agent_cfg is None:
            available = [aid for aid, _ in iter_agents(config)]
            raise ValueError(
                f"Agent '{target_id}' not found in scenario.yaml. "
                f"Available agents: {available}"
            )

        scenario_dir = get_scenario_dir()
        prompts_dir = scenario_dir / "data" / "prompts" if scenario_dir else Path(".")
        instructions_spec = agent_cfg.get("instructions", [])
        prompt_text = load_instructions(instructions_spec, prompts_dir, None)
        display_name = agent_cfg.get("name", target_id)

        return target_id, display_name, prompt_text

    def list_definitions(self) -> list[dict[str, Any]]:
        """Return metadata for all agents defined in scenario.yaml.

        Returns:
            List of dicts with keys: id, name, description, tools,
            tool_count, is_default.
        """
        config = load_agents_block()
        default_id = get_default_id(config)
        entries = iter_agents(config)

        result: list[dict[str, Any]] = []
        for agent_id, agent_cfg in entries:
            tools = list(agent_cfg.get("tools", []))
            ui_metadata = _extract_agent_ui_metadata(agent_cfg)
            result.append({
                "id": agent_id,
                "name": agent_cfg.get("name", agent_id),
                "description": (agent_cfg.get("description", "") or "").strip(),
                "tools": tools,
                "tool_count": len(tools),
                "is_default": agent_id == default_id,
                **ui_metadata,
            })
        return result

    def get_agent_prompt_for_router(self, agent_id: str | None = None) -> dict:
        """Return prompt details for GET /api/scenario/agent-prompt endpoint.

        Args:
            agent_id: Agent to inspect. None = use default.

        Returns:
            Dict with agent_id, agent_name, instruction_files, prompt_text, char_count.
        """
        from app.scenario import get_scenario_dir

        scenario_dir = get_scenario_dir()
        if not scenario_dir:
            return {"error": "No active scenario configured", "prompt_text": ""}

        prompts_dir = scenario_dir / "data" / "prompts"

        try:
            config = load_agents_block()
        except ValueError as e:
            return {"error": str(e), "prompt_text": ""}

        target_id = agent_id or get_default_id(config)
        if not target_id:
            return {"error": "No agent_id specified and no default configured", "prompt_text": ""}

        agent_cfg = find_agent(config, target_id)
        if not isinstance(agent_cfg, dict):
            available = [aid for aid, _ in iter_agents(config)]
            return {"error": f"Agent '{target_id}' not found. Available: {available}", "prompt_text": ""}

        agent_name = agent_cfg.get("name", target_id)
        instruction_files = agent_cfg.get("instructions", [])
        prompt_text = load_instructions(instruction_files, prompts_dir)

        return {
            "agent_id": target_id,
            "agent_name": agent_name,
            "instruction_files": instruction_files,
            "prompt_text": prompt_text,
            "char_count": len(prompt_text),
        }

    def invalidate(self) -> None:
        """Clear config cache. Called on scenario switch."""
        invalidate_cache()


# Module-level singleton — the one instance callers import.
registry = AgentRegistry()
