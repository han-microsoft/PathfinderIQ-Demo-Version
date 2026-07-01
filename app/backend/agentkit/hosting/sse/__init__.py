"""agentkit.hosting.sse — the generic SSE transport spine package (S1/S2/B1).

Three concerns, one package:

    - ``_core`` — frame formatters (``format_sse`` / ``format_sse_wire``) and
      the domain-extensible event-name vocabulary
      (``GENERIC_EVENT_NAMES`` / ``register_domain_events`` / ``known_event_names``).
    - ``service`` — generic stream-orchestration mechanics
      (``wrap_stream_with_keepalive`` keepalive/abort/delegation wrapper +
      ``accumulate_stream_event`` turn projection).
    - ``disconnect`` — ASGI client-disconnect-aware producer wrapper
      (``sse_with_disconnect``).

Domain-blind: imports ``agentkit.contracts``, ``agentkit.config``,
``agentkit.guardrails`` and stdlib only. A consumer registers its domain SSE
event names on top of the generic vocabulary via ``register_domain_events``
(the vocabulary is data the consumer extends, not a code-fork).
"""

from agentkit.hosting.sse._core import (
    GENERIC_EVENT_NAMES,
    GENERIC_TERMINALS,
    format_sse,
    format_sse_wire,
    is_known_event,
    known_event_names,
    register_domain_events,
)
from agentkit.hosting.sse.service import (
    accumulate_stream_event,
    wrap_stream_with_keepalive,
)
from agentkit.hosting.sse.disconnect import sse_with_disconnect

__all__ = [
    "GENERIC_EVENT_NAMES",
    "GENERIC_TERMINALS",
    "format_sse",
    "format_sse_wire",
    "is_known_event",
    "known_event_names",
    "register_domain_events",
    "accumulate_stream_event",
    "wrap_stream_with_keepalive",
    "sse_with_disconnect",
]
