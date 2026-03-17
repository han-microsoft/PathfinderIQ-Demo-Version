"""create_incident_ticket — create a formal incident ticket (spoofed).

Module role:
    Spoofed incident management tool. Generates a realistic incident
    ticket ID and returns structured JSON confirming ticket creation.
    Logs the action to session-scoped spoof state.

Key collaborators:
    - tools._spoof_state.log_action — records ticket creation in action log
    - app.request_context.get_session_id — session isolation key

Dependents:
    Imported by: tools/incidents/__init__.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)


@tool
@traced_tool("create_incident_ticket", backend="spoof")
async def create_incident_ticket(
    severity: Annotated[str, Field(
        description="Severity level: 'SEV-1', 'SEV-2', 'SEV-3', or 'SEV-4'.",
    )],
    title: Annotated[str, Field(
        description="Short incident title.",
    )],
    description: Annotated[str, Field(
        description="Detailed incident description.",
    )],
    affected_services: Annotated[str, Field(
        description="Comma-separated affected service IDs.",
    )],
    assigned_to: Annotated[str, Field(
        description="Engineer or team assigned to the ticket.",
    )] = "NOC",
    **kwargs: Any,
) -> str:
    """Create a formal incident ticket (spoofed — returns realistic JSON).

    Generates a timestamped ticket ID and logs the creation in the
    session's action log. Returns structured JSON with ticket details.

    Args:
        severity: Incident severity level.
        title: Short descriptive title.
        description: Full incident description.
        affected_services: Comma-separated service IDs.
        assigned_to: Assignee name or team.

    Returns:
        JSON string with ticket_id, status, severity, and URL.

    Side effects:
        Writes to spoof state action log.
    """
    # Import lazily to avoid circular deps at module load time
    from app.foundation.request_context import get_session_id
    from tools._spoof_state import log_action

    sid = get_session_id()
    # Generate a realistic timestamped ticket ID
    ticket_id = f"INC-{datetime.now(timezone.utc).strftime('%Y-%m%d-%H%M%S')}"

    log_action(sid, "create_incident_ticket", ticket_id=ticket_id,
               severity=severity, title=title)

    logger.info(
        "tool.create_incident_ticket.executed",
        extra={"session_id": sid, "ticket_id": ticket_id, "severity": severity},
    )

    return json.dumps({
        "ticket_id": ticket_id,
        "status": "open",
        "severity": severity,
        "title": title,
        "assigned_to": assigned_to,
        "url": f"https://incidents.austtelco.internal/tickets/{ticket_id}",
    })
