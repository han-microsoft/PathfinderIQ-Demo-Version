"""Agent roster context provider (K6) — injects available agents list.

Module role:
    Reads agent definitions from config and formats them as an instruction block
    for the LLM's awareness of available agents.

Layering:
    stdlib + ``agentkit.core.config_loader`` (lazy). No GridIQ package. Was
    ``agent/providers/roster.py``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentRosterProvider:
    """Injects the available agent roster as a context instruction.

    Reads agent definitions from the agent config and formats them as a bullet
    list for the LLM's awareness.

    Attributes:
        source_id: Provider identifier for message attribution.
    """

    def __init__(self) -> None:
        """Initialise the roster provider with its source identifier."""
        self.source_id = "agent_roster"

    async def before_run(self, *, agent: Any, session: Any, context: Any, state: dict) -> None:
        """Inject agent roster as instruction before each agent.run()."""
        try:
            from agentkit.core.config_loader import load_agents_block, iter_agents, get_default_id

            config = load_agents_block()
            entries = list(iter_agents(config))
            if not entries:
                return

            default_id = get_default_id(config)
            lines = ["## Available Agents", ""]
            for agent_id, agent_cfg in entries:
                name = str(agent_cfg.get("name", agent_id)).strip() or agent_id
                desc = str(agent_cfg.get("description", "")).strip()
                suffix = " (default)" if agent_id == default_id else ""
                line = f"- `{agent_id}`{suffix} — {name}"
                if desc:
                    line += f": {desc}"
                lines.append(line)
            lines.append("")
            lines.append("Do not invent agent IDs or reuse agents from other scenarios.")

            roster_text = "\n".join(lines)
            context.extend_instructions(self.source_id, roster_text)
            logger.debug("provider.roster.injected: %d agents", len(entries))
        except Exception as e:
            logger.debug("provider.roster.skipped: %s", e)

    async def after_run(self, *, agent: Any, session: Any, context: Any, state: dict) -> None:
        """No-op — roster is read-only context."""
        pass
