"""Per-session abort event registry — shared between chat router and delegation tool.

Module role:
    Holds the dict of active generation abort events, keyed by
    ``(session_id, agent_id)``. Lives in foundation so both the chat
    router (L4) and the delegation tool (L3) can import it without
    creating a cross-layer dependency.

Key collaborators:
    - ``app.routers.chat`` — creates and consumes abort events
    - ``tools.delegation``  — reads abort events during specialist streaming
    - ``tests/unit/test_abort_cascade.py`` — verifies abort semantics

Dependents:
    Called by: chat.py, delegation/__init__.py, test_abort_cascade.py
"""

from __future__ import annotations

import asyncio

# Active generation abort events, keyed by (session_id, agent_id).
# Set by the chat router when a generation starts; checked by the
# delegation tool and keepalive wrapper during streaming.
abort_events: dict[tuple[str, str], asyncio.Event] = {}
