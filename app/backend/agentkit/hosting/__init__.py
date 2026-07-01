"""agentkit.hosting — the generic SSE transport spine (S1/S2/S4).

The ``[fastapi]`` extra layer per the Tier-1 plan §4. Domain-blind: imports
``agentkit.contracts``, ``agentkit.config`` and stdlib only. A consumer
registers its domain SSE event names on top of the generic vocabulary via
``register_domain_events`` (the vocabulary is data the consumer extends, not
a code-fork).

Public surface:
    - ``format_sse`` / ``format_sse_wire`` — SSE frame formatters.
    - ``GENERIC_EVENT_NAMES`` / ``GENERIC_TERMINALS`` — the generic vocabulary.
    - ``register_domain_events`` / ``known_event_names`` / ``is_known_event``.
    - ``ToolCallBuffer`` / ``map_update_to_events`` / ``extract_usage`` /
      ``extract_user_message`` — SDK update → SSE event mapper.
    - ``abort_events`` + registry helpers — single-flight abort registry.
    - ``parse_sse_frames`` / ``check_event_sequence`` — live contract probe core.
    - ``run_agent_stream`` — the generic streaming agent run engine (Inc13b).
    - run-loop driver + ``Run*`` event types, completion-check helpers.
"""

from agentkit.hosting.sse import (
    GENERIC_EVENT_NAMES,
    GENERIC_TERMINALS,
    format_sse,
    format_sse_wire,
    is_known_event,
    known_event_names,
    register_domain_events,
)
from agentkit.hosting.event_mapping import (
    ToolCallBuffer,
    extract_usage,
    extract_user_message,
    map_update_to_events,
)
from agentkit.hosting.abort_registry import (
    abort_events,
    cleanup_stale_entries,
    register_abort_event,
    try_register_abort_event,
    unregister_abort_event,
)
from agentkit.hosting.probe import check_event_sequence, parse_sse_frames
from agentkit.hosting.run_loop import (
    AgentRunAbortedError,
    AgentRunStalledError,
    RunProgress,
)
from agentkit.hosting.run_engine import run_agent_stream

__all__ = [
    "GENERIC_EVENT_NAMES",
    "GENERIC_TERMINALS",
    "format_sse",
    "format_sse_wire",
    "is_known_event",
    "known_event_names",
    "register_domain_events",
    "ToolCallBuffer",
    "extract_usage",
    "extract_user_message",
    "map_update_to_events",
    "abort_events",
    "cleanup_stale_entries",
    "register_abort_event",
    "try_register_abort_event",
    "unregister_abort_event",
    "check_event_sequence",
    "parse_sse_frames",
    "run_agent_stream",
    "AgentRunAbortedError",
    "AgentRunStalledError",
    "RunProgress",
]
