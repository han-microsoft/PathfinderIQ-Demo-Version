"""agentkit.hosting.runtime — generic FastAPI/ASGI runtime building blocks.

Domain-blind runtime helpers that sit beneath the SSE transport spine:

    - ``BoundedEventChannel`` — bounded-queue + rate-limited categorical
      overflow-marker policy (visible-overflow discipline).
    - ``providers`` — lightweight reference LLM providers (Echo, Mock) with
      zero external dependencies, used by quickstarts, demos, and SSE
      pipeline tests.

Imports ``agentkit.contracts`` / ``agentkit.config`` / stdlib only. Imports
zero consumer (GridIQ) packages — the concrete provider-selection factory
lives in the consumer's composition root and imports these classes.
"""

from agentkit.hosting.runtime.bounded_channel import (
    DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS,
    BoundedEventChannel,
)

__all__ = [
    "BoundedEventChannel",
    "DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS",
]
