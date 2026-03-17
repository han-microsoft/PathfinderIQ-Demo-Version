"""reroute_traffic — activate a backup MPLS path to reroute traffic.

Module role:
    Spoofed network action tool. Simulates activating an MPLS backup
    path by writing to the session-scoped spoof state. Returns realistic
    JSON confirming the traffic reroute.

Key collaborators:
    - tools._spoof_state.activate_route — writes route activation state
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
@traced_tool("reroute_traffic", backend="spoof")
async def reroute_traffic(
    backup_path_id: Annotated[str, Field(
        description="MPLS backup path ID to activate (e.g., 'MPLS-BACKUP-02').",
    )],
    reason: Annotated[str, Field(
        description="Why rerouting is needed.",
    )] = "",
    **kwargs: Any,
) -> str:
    """Activate a backup MPLS path to reroute traffic away from a failed link.

    Writes the activation to session-scoped spoof state so subsequent
    graph queries reflect the reroute. Returns JSON confirming the action.

    Args:
        backup_path_id: MPLS backup path ID.
        reason: Human-readable reason for the reroute.

    Returns:
        JSON string with status, path, and activation timestamp.

    Side effects:
        Writes to spoof state via activate_route().
    """
    # Import lazily to avoid circular deps at module load time
    from app.foundation.request_context import get_session_id
    from tools._spoof_state import activate_route

    sid = get_session_id()
    result = activate_route(sid, backup_path_id, reason=reason)

    logger.info(
        "tool.reroute_traffic.executed",
        extra={"session_id": sid, "path": backup_path_id, "reason": reason},
    )

    return json.dumps({
        "status": "rerouted",
        "path": backup_path_id,
        **result,
    })
