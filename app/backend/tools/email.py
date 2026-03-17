"""send_incident_report — simulated email dispatch for situation reports.

Module role:
    Simulates sending a structured incident report to a NOC mailing list.
    In production this would integrate with an email API (SendGrid, SES,
    Exchange). For the demo, it formats the report and returns a
    confirmation with a message ID.

Key collaborators:
    - ``agent_framework.tool`` — ``@tool`` decorator for JSON schema generation
    - Orchestrator agent — calls this as the final step of every investigation

Dependents:
    Imported by: ``agents`` (AgentRegistry) via scenario.yaml tool spec
    ``tools.email:send_incident_report``
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)

# Simulated NOC distribution list
_NOC_MAILING_LIST = "noc-alerts@austtelco.com.au"
_CC_LIST = "noc-management@austtelco.com.au, sla-compliance@austtelco.com.au"


@tool(approval_mode="never_require")
@traced_tool("send_incident_report", backend="default")
async def send_incident_report(
    subject: Annotated[str, Field(
        description=(
            "Email subject line. Format: "
            "'[SEVERITY] Component — Short description'. "
            "Example: '[CRITICAL] LINK-SYD-MEL-FIBRE-01 — Fibre cut on SYD-MEL corridor'"
        ),
    )],
    report: Annotated[str, Field(
        description=(
            "The full situation report in markdown. Must include all sections: "
            "Incident Summary, Blast Radius, Root Cause Analysis, Evidence Summary, "
            "SOP Actions (from runbooks), Historical Precedents (from tickets), "
            "Actions Taken (dispatch details), and Recommended Next Steps."
        ),
    )],
    severity: Annotated[str, Field(
        description="Incident severity: 'CRITICAL', 'MAJOR', 'WARNING', or 'MINOR'.",
    )] = "CRITICAL",
) -> str:
    """Send the final incident situation report to the NOC mailing list."""
    send_time = datetime.now(timezone.utc).isoformat()
    message_id = f"MSG-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    result = {
        "status": "sent",
        "message_id": message_id,
        "timestamp": send_time,
        "to": _NOC_MAILING_LIST,
        "cc": _CC_LIST,
        "subject": subject,
        "severity": severity,
        "report_length_chars": len(report),
    }

    logger.info(
        "Incident report sent: %s | To: %s | Subject: %s | Length: %d chars",
        message_id, _NOC_MAILING_LIST, subject, len(report),
    )

    return json.dumps(result)
