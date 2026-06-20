"""agentkit.persistence — session-store layer (F3).

Generic session-persistence kernel:
    - :mod:`agentkit.persistence.protocol`  — the domain-blind ``SessionStore``
      protocol (CRUD + per-agent threads + lifecycle).
    - :mod:`agentkit.persistence.memory`    — pure ``InMemorySessionStore``
      (stdlib only — the quickstart default and Phase-1 fallback).
    - :mod:`agentkit.persistence.cosmos`    — ``CosmosContainerStore`` base
      (``[cosmos]`` extra; B-COSMOS-ASYNCIO baked in). The concrete Cosmos
      client is injected by the consumer, so importing this subpackage's
      ``protocol`` / ``memory`` pulls **no** azure dependency.

``cosmos`` is intentionally NOT re-exported here — importing it eagerly would
drag the azure surface into the base import path. Import it explicitly
(``from agentkit.persistence.cosmos import CosmosContainerStore``) behind the
``[cosmos]`` extra.
"""

from __future__ import annotations

from agentkit.persistence.memory import InMemorySessionStore
from agentkit.persistence.protocol import SessionStore

__all__ = ["SessionStore", "InMemorySessionStore"]
