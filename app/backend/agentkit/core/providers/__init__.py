"""Agent context providers (K6) — participate in the SDK context pipeline.

Package role:
    Provider implementations that add context before ``agent.run()`` (via
    ``before_run``) and optionally process the response after (via
    ``after_run``). Each provider is a self-contained, duck-typed unit with
    injected dependencies. Domain-blind: imports no GridIQ package.

    ``SessionHistoryProvider`` was named ``GridIQHistoryProvider`` in GridIQ; the
    GridIQ shim re-exports it under the old name for back-compat.
"""

from agentkit.core.providers.roster import AgentRosterProvider
from agentkit.core.providers.time import (
    SystemTimeProvider,
    get_current_time,
    set_time_context_note,
)
from agentkit.core.providers.history import SessionHistoryProvider
from agentkit.core.providers.memory import CosmosUserMemoryProvider
from agentkit.core.providers._factory import (
    create_static_providers,
    create_per_request_providers,
)

__all__ = [
    "AgentRosterProvider",
    "SystemTimeProvider",
    "SessionHistoryProvider",
    "CosmosUserMemoryProvider",
    "get_current_time",
    "set_time_context_note",
    "create_static_providers",
    "create_per_request_providers",
]
