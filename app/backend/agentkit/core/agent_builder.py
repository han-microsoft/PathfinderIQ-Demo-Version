"""Agent build helpers — cache-keyed agent construction + provider injection.

Module role:
    SDK-agnostic, domain-blind helpers for per-request agent preparation:
    per-agent reflection-config lookup, cache-keyed agent build, and
    per-request context-provider injection. Lifted from GridIQ's
    ``hosting/fastapi/runtime/_agent_build.py`` (Inc13b) so the chat-runtime
    orchestration lives in agentkit.

    Pure functions taking the registry/cache/user-memory deps as parameters
    — no class state. A consumer's runtime retains thin wrappers that pass
    in its own registry / cache / middleware / user-memory container.

Layer rule:
    ``agentkit.core`` only. Zero SDK import (the agent is duck-typed). Zero
    consumer/domain import.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_reflection_settings(agent_id: str) -> tuple[bool, int]:
    """Read per-agent reflection settings from the agent config.

    Returns ``(enabled, max_rounds)`` with safe defaults when the agent
    does not declare reflection. Logs the resolved values once per call
    so the run trace records which agent ran with reflection.
    """
    from agentkit.core.config_loader import find_agent, get_default_id, load_agents_block

    config = load_agents_block()
    target_id = agent_id or get_default_id(config)
    agent_cfg = find_agent(config, target_id) or {}

    # Require explicit opt-in via the config key — no implicit defaults.
    enabled = bool(agent_cfg.get("reflection", False))
    max_rounds_raw = agent_cfg.get("max_reflection_rounds", 2)
    try:
        max_rounds = max(1, int(max_rounds_raw))
    except (TypeError, ValueError):
        max_rounds = 2
    logger.info(
        "reflection.settings: agent_id=%s enabled=%s max_rounds=%d",
        target_id,
        enabled,
        max_rounds,
    )
    return enabled, max_rounds


def prepare_agent(
    *,
    agent_registry: Any,
    agent_cache: dict[tuple[str, str], Any],
    middleware: Any,
    default_agent_id: str,
    user_memory_container: Any | None,
    current_model: str,
    agent_id: str,
    session_id: str,
    user_oid: str,
    store: Any,
) -> Any:
    """Build or load one cached agent, then inject per-request providers.

    Centralises the agent-cache lookup and provider injection so the
    primary run path and reflection path use the same request-scoped
    agent preparation logic.

    Returns:
        Prepared agent instance ready for ``agent.run()``.

    Side effects:
        May populate ``agent_cache`` and may shallow-copy the cached
        agent to isolate request-scoped providers.
    """
    cache_key = (agent_id or "default", current_model)
    if cache_key in agent_cache:
        agent = agent_cache[cache_key]
    else:
        agent = agent_registry.build(
            agent_id or None,
            model_override=current_model,
            middleware=middleware or None,
        )
        agent_cache[cache_key] = agent

    from agentkit.core.providers import create_per_request_providers

    per_request = create_per_request_providers(
        user_oid=user_oid,
        session_id=session_id,
        store=store,
        agent_id=agent_id or default_agent_id,
        memory_container=user_memory_container,
        memory_container_resolver=None,
    )
    if per_request and hasattr(agent, "context_providers"):
        agent = copy.copy(agent)
        static_ids = {getattr(provider, "source_id", "") for provider in per_request}
        agent.context_providers = per_request + [
            provider for provider in agent.context_providers
            if getattr(provider, "source_id", "") not in static_ids
        ]
    return agent


__all__ = ["get_reflection_settings", "prepare_agent"]
