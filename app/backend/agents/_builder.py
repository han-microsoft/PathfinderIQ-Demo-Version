"""Agent builder — constructs SDK Agent objects from config dicts.

Module role:
    Takes a single agent's config dict (name, description, instructions,
    tools, model), loads its prompt text, resolves its tool callables, reads
    the per-agent model from scenario.yaml, and calls ``client.as_agent()``
    to produce an SDK Agent object. This module owns SDK construction only —
    no YAML parsing, no caching, no session management.

    Model resolution priority:
      1. _MODEL_OVERRIDE env var (transient — set by retry/fallback loop)
      2. agent_cfg["model"] from scenario.yaml
      3. settings.llm_model global default

Key collaborators:
    - agents._prompts — load_instructions()
    - agents._tools   — resolve_tools()

Dependents:
    Imported by: agents/__init__.py (AgentRegistry.build) only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.foundation.config import settings
from agents._prompts import load_instructions
from agents._tools import resolve_tools

logger = logging.getLogger(__name__)


def build_agent(
    agent_id: str,
    agent_cfg: dict[str, Any],
    prompts_dir: Path,
    preamble_path: Path | None,
    client: Any,
    *,
    model_override: str = "",
    middleware: Any | None = None,
    context_providers: Any | None = None,
) -> Any:
    """Build an SDK Agent from a config dict.

    Args:
        agent_id: The config key identifying this agent (e.g. "orchestrator").
        agent_cfg: The agent's config dict with name, description, instructions, tools.
        prompts_dir: Path to the scenario's data/prompts/ directory.
        preamble_path: Path to the generic preamble file (prepended first). None to skip.
        client: An AzureAIAgentClient (or compatible) instance.
        model_override: Explicit model override from retry/fallback loop. Takes priority
            over scenario.yaml and settings. Empty = use scenario/settings default.
        middleware: Optional SDK middleware instances forwarded to client.as_agent().
        context_providers: Optional BaseContextProvider instances forwarded to client.as_agent().

    Returns:
        An Agent object built via client.as_agent().
    """
    name = agent_cfg.get("name", agent_id)
    description = agent_cfg.get("description", "")

    # Load prompt text from instruction file specs
    instructions_spec = agent_cfg.get("instructions", [])
    instructions = load_instructions(instructions_spec, prompts_dir, preamble_path)
    if not instructions:
        logger.warning("Agent '%s' has empty instructions", name)

    # Resolve tool callables from spec strings
    tool_specs = agent_cfg.get("tools", [])
    tools = resolve_tools(tool_specs)

    tool_names = [getattr(t, "name", str(t)) for t in tools]
    logger.info("Agent '%s': %d tools loaded: %s", name, len(tools), tool_names)

    # Model resolution priority:
    #   1. model_override parameter (set by retry/fallback loop in agent.py)
    #   2. Per-agent model: key from scenario.yaml
    #   3. Global default from settings.llm_model
    model = model_override or agent_cfg.get("model") or settings.llm_model
    source = "retry_override" if model_override else ("scenario.yaml" if agent_cfg.get("model") else "settings.llm_model")
    logger.info("Agent '%s': using model '%s' (source=%s)", name, model, source)

    # Build the SDK agent — parallel tool calls disabled for sequential narrative
    agent = client.as_agent(
        name=name,
        description=description,
        instructions=instructions,
        tools=tools or None,
        default_options={"allow_multiple_tool_calls": False, "model_id": model},
        middleware=middleware,
        context_providers=context_providers,
    )

    logger.info(
        "Agent '%s' (id=%s) built: %d tools, %d chars instructions",
        name, agent_id, len(tools), len(instructions),
    )
    return agent
