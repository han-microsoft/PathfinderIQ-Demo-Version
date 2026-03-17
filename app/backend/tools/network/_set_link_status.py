"""set_link_status — change a transport link's operational status.

Module role:
    Spoofed network action tool. Simulates changing a transport link's
    status (admin_down / admin_up) by writing to the session-scoped spoof
    state. Subsequent query_graph calls read the overlay.

Key collaborators:
    - tools._spoof_state.set_link_status — writes link status override
    - app.request_context.get_session_id — session isolation key

Dependents:
    Imported by: tools/network/__init__.py
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)


@tool
@traced_tool("set_link_status", backend="spoof")
async def set_link_status(
    link_id: Annotated[str, Field(
        description="Transport link ID (e.g., 'LINK-SYD-MEL-FIBRE-01').",
    )],
    status: Annotated[str, Field(
        description="Target status: 'admin_down' or 'admin_up'.",
    )],
    **kwargs: Any,
) -> str:
    """Change a transport link's operational status (admin-down or admin-up).

    Writes the status override to session-scoped spoof state so subsequent
    query_graph calls reflect the change. Returns JSON confirming the action.

    Args:
        link_id: Transport link ID.
        status: Target operational status.

    Returns:
        JSON string with status, link, and change timestamp.

    Side effects:
        Writes to spoof state via _spoof_state.set_link_status().
    """
    # Import lazily to avoid circular deps at module load time
    from app.foundation.request_context import get_session_id
    from tools._spoof_state import set_link_status as _set

    sid = get_session_id()
    result = _set(sid, link_id, status)

    logger.info(
        "tool.set_link_status.executed",
        extra={"session_id": sid, "link_id": link_id, "status": status},
    )

    return json.dumps({
        "status": status,
        "link": link_id,
        **result,
    })
