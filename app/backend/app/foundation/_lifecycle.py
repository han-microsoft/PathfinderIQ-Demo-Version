"""Application lifecycle signals — shared between main.py and routers.

Module role:
    Holds the ``shutdown_event`` that signals active SSE generators to drain
    gracefully. Extracted from ``main.py`` to break the circular import:
    ``main.py → routers/chat.py → main.py``.

    ``main.py`` sets this event during lifespan teardown.
    ``routers/chat.py`` checks this event on each streaming iteration.

Key collaborators:
    - app.main (lifespan)    — calls ``shutdown_event.set()`` during shutdown
    - app.routers.chat       — checks ``shutdown_event.is_set()`` during streaming

Dependents:
    Imported by: app.main, app.routers.chat
"""

from __future__ import annotations

import asyncio

# Set during lifespan teardown so active SSE generators can drain gracefully
# instead of being killed mid-stream. Checked by chat.py's event_generator
# on each streaming iteration.
shutdown_event = asyncio.Event()
