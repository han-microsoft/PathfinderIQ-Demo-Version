"""Agent builder (K4) — constructs SDK Agent objects from config dicts.

Module role:
    Takes a single agent's config dict (name, description, instructions, tools,
    model), loads its prompt text, resolves its tool callables, reads the
    per-agent model from settings/config, and calls ``client.as_agent()`` to
    produce an SDK Agent object. Owns SDK construction only — no YAML parsing,
    no caching, no session management.

    The ``client`` parameter satisfies ``core.AgentClient``; this module never
    imports a concrete SDK client — the consumer's composition root injects one
    (§3.3). The SDK seam is the ``as_agent`` call.

    Model resolution priority:
        1. ``model_override`` parameter from the retry/fallback loop
        2. ``agent_cfg["model"]`` from agent_config.yaml ("fast" aliases to
           ``settings.llm_model_fast``)
        3. ``settings.llm_model`` global default

Layering:
    Imports ``agentkit.config`` (settings) + ``agentkit.core`` siblings. No
    GridIQ package. Was ``agent/_builder.py``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agentkit.config import get_settings
from agentkit.core.prompt_loader import load_instructions
from agentkit.core.tool_resolver import resolve_tools
from agentkit.core.compaction import create_compaction_strategy
from agentkit.core.providers import create_static_providers

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
        agent_id: The config key identifying this agent (e.g. "controller").
        agent_cfg: The agent's config dict with name, description, instructions, tools.
        prompts_dir: Path to the ``control/prompts/`` directory.
        preamble_path: Path to the generic preamble file (prepended first). None to skip.
        client: An object satisfying ``core.AgentClient`` (e.g. AzureAIAgentClient).
        model_override: Explicit model override from retry/fallback loop. Takes
            priority over config and settings. Empty = use config/settings default.
        middleware: Optional SDK middleware instances forwarded to client.as_agent().
        context_providers: Optional context providers forwarded to client.as_agent().

    Returns:
        An Agent object built via ``client.as_agent()``.
    """
    settings = get_settings()
    name = agent_cfg.get("name", agent_id)
    description = agent_cfg.get("description", "")

    # Load prompt text from instruction file specs
    instructions_spec = agent_cfg.get("instructions", [])
    instructions = load_instructions(instructions_spec, prompts_dir, preamble_path)

    # Prepend foundation prompts (knowledge shared by all agents), loaded from
    # the top-level ``foundation_prompts`` key in agent_config.yaml.
    from agentkit.core.prompt_loader import load_foundation_prompts
    foundation = load_foundation_prompts()
    if foundation:
        instructions = f"{foundation}\n\n{instructions}" if instructions else foundation

    if not instructions:
        logger.warning("Agent '%s' has empty instructions", name)

    # Resolve tool callables from spec strings (fail-loud on a bad spec).
    tool_specs = agent_cfg.get("tools", [])
    tools = resolve_tools(tool_specs)

    # Bind agentkit-marked tool callables (``@agentkit.tools.tool``) to the
    # concrete SDK at build time. For a MAF client this wraps each marked
    # callable with the real ``agent_framework.tool(approval_mode=...)`` — the
    # SDK seam lives in ``agentkit.sdk.maf_client`` (lazy SDK import). For a
    # non-MAF client (echo/mock) the marker is ignored and raw callables are
    # used. Imported lazily so the core builder stays SDK-free at module load.
    from agentkit.sdk.maf_client import bind_tools
    tools = bind_tools(tools, client)

    tool_names = [getattr(t, "name", str(t)) for t in tools]
    logger.info("Agent '%s': %d tools loaded: %s", name, len(tools), tool_names)

    # Model resolution priority (see module docstring).
    raw_model = model_override or agent_cfg.get("model") or settings.llm_model
    if raw_model == "fast":
        model = settings.llm_model_fast or settings.llm_model
        source = "fast_alias"
    else:
        model = raw_model
        source = "retry_override" if model_override else ("config" if agent_cfg.get("model") else "settings.llm_model")
    logger.info("Agent '%s': using model '%s' (source=%s)", name, model, source)

    # Roster provider inclusion is config-driven. Inferred default = "include if
    # any tool spec contains 'delegate_to_agent'"; an explicit
    # ``include_roster: true|false`` in config overrides.
    inferred_roster = any("delegate_to_agent" in str(s) for s in tool_specs)
    include_roster = bool(agent_cfg.get("include_roster", inferred_roster))
    static_providers = create_static_providers(include_roster=include_roster)
    all_providers = list(context_providers or []) + static_providers

    # Parallel tool calls — configurable per-agent (default: sequential for narrative)
    parallel_tools = agent_cfg.get("parallel_tool_calls", False)
    agent = client.as_agent(
        name=name,
        description=description,
        instructions=instructions,
        tools=tools or None,
        default_options={"allow_multiple_tool_calls": parallel_tools, "model_id": model},
        middleware=middleware,
        context_providers=all_providers,
    )

    # Attach compaction strategy post-construction. Per-agent ``compaction:
    # false`` suppresses it for stateless agents.
    compaction_enabled = bool(agent_cfg.get("compaction", True))
    if not compaction_enabled:
        logger.info("Agent '%s': compaction disabled by config", name)
    elif not getattr(agent, "_compaction_strategy", None):
        _strategy = create_compaction_strategy()
        if _strategy is not None:
            agent._compaction_strategy = _strategy
            logger.info("Agent '%s': compaction strategy attached", name)

    logger.info(
        "Agent '%s' (id=%s) built: %d tools, %d chars instructions",
        name, agent_id, len(tools), len(instructions),
    )
    return agent
