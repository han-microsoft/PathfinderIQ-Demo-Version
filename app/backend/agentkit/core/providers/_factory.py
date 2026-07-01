"""Provider factory functions (K6) — creates static and per-request provider lists.

Module role:
    Factory functions that construct provider instances for the agent pipeline.
    The consumer's hosting layer owns infrastructure construction; this module
    only wires already-resolved dependencies into provider instances.

Layering:
    Imports ``agentkit.core.providers`` siblings (lazy). No GridIQ package. Was
    ``agent/providers/_factory.py``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_static_providers(*, include_roster: bool = True) -> list:
    """Create context providers that don't depend on per-request state.

    Args:
        include_roster: Include the roster provider. False for agents without
            delegation.

    Returns:
        List of provider instances in execution order.
    """
    from agentkit.core.providers.time import SystemTimeProvider
    providers: list = []
    if include_roster:
        from agentkit.core.providers.roster import AgentRosterProvider
        providers.append(AgentRosterProvider())
    providers.append(SystemTimeProvider())
    logger.info("providers.static.created: %d provider(s)", len(providers))
    return providers


def create_per_request_providers(
    user_oid: str = "",
    session_id: str = "",
    store: Any = None,
    agent_id: str = "",
    memory_container: Any = None,
    memory_container_resolver: Any = None,
) -> list:
    """Create context providers that depend on per-request state.

    These are created fresh per-request because they reference user-specific or
    session-specific data.

    Args:
        user_oid: User's object ID. Empty = skip memory.
        session_id: Current session ID.
        store: Session store instance. None = skip history.
        agent_id: Agent config key. Empty = skip history.
        memory_container: Pre-resolved Cosmos container proxy for user memory.
        memory_container_resolver: Async callable used when the container must be
            resolved lazily outside this package.

    Returns:
        List of per-request provider instances. May be empty.
    """
    from agentkit.core.providers.history import SessionHistoryProvider
    providers: list = []

    # History provider — loads conversation from the session store
    if store and session_id and agent_id:
        providers.append(SessionHistoryProvider(store, session_id, agent_id))

    # User memory provider — loads per-user facts from Cosmos
    if user_oid:
        try:
            from agentkit.core.providers.memory import CosmosUserMemoryProvider
            providers.append(CosmosUserMemoryProvider(
                user_oid=user_oid,
                session_id=session_id,
                container_client=memory_container,
                container_resolver=memory_container_resolver,
            ))
        except Exception as e:
            logger.debug("providers.memory.skipped: %s", e)

    return providers
