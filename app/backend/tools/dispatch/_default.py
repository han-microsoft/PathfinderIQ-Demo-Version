"""dispatch_field_engineer — function tool for the orchestrator agent.

Module role:
    Simulates dispatching a field engineer by composing a structured dispatch
    notification email with incident details, GPS coordinates, inspection
    checklist, and triggering sensors. In production, this would integrate
    with email APIs, push notification services, or ticketing systems.

    The tool generates a formal dispatch document with:
    - Dispatch ID (timestamped)
    - Engineer contact details (name, email, phone)
    - Incident summary
    - GPS location with Google Maps link
    - Physical inspection checklist
    - Triggering sensor IDs

Key collaborators:
    - ``agent_framework.tool`` – ``@tool`` decorator for JSON schema generation
    - Orchestrator agent – calls this tool after completing investigation

Dependents:
    Imported by: ``tools/__init__.py`` (ORCHESTRATOR_TOOLS)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)


@tool
@traced_tool("dispatch_field_engineer", backend="default")
async def dispatch_field_engineer(
    engineer_name: Annotated[str, Field(
        description="Full name of the on-duty field engineer from the duty roster.",
    )],
    engineer_email: Annotated[str, Field(
        description="Email address of the field engineer.",
    )],
    engineer_phone: Annotated[str, Field(
        description="Phone number of the field engineer.",
    )],
    incident_summary: Annotated[str, Field(
        description="Brief summary of the incident and why dispatch is needed.",
    )],
    destination_description: Annotated[str, Field(
        description="Human-readable description of where to go (e.g. 'Goulburn interchange splice point').",
    )],
    destination_latitude: Annotated[float, Field(
        description="GPS latitude (WGS84) of the inspection site.",
    )],
    destination_longitude: Annotated[float, Field(
        description="GPS longitude (WGS84) of the inspection site.",
    )],
    physical_signs_to_inspect: Annotated[str, Field(
        description="Checklist of what to look for on arrival.",
    )],
    sensor_ids: Annotated[str, Field(
        description="Comma-separated sensor IDs that triggered the dispatch.",
    )],
    urgency: Annotated[str, Field(
        description="Urgency level — 'CRITICAL', 'HIGH', or 'STANDARD'.",
    )] = "HIGH",
) -> str:
    """Dispatch a field engineer to a physical site to investigate a network incident."""
    dispatch_time = datetime.now(timezone.utc).isoformat()
    dispatch_id = f"DISPATCH-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    maps_link = f"https://www.google.com/maps?q={destination_latitude},{destination_longitude}"

    email_body = f"""FIELD DISPATCH NOTIFICATION
{'=' * 50}

Dispatch ID:  {dispatch_id}
Urgency:      {urgency}
Dispatched:   {dispatch_time}

TO: {engineer_name}
Email: {engineer_email}
Phone: {engineer_phone}

{'─' * 50}
INCIDENT SUMMARY
{'─' * 50}
{incident_summary}

{'─' * 50}
DESTINATION
{'─' * 50}
Location: {destination_description}
GPS:      {destination_latitude}, {destination_longitude}
Map:      {maps_link}

{'─' * 50}
INSPECTION CHECKLIST
{'─' * 50}
{physical_signs_to_inspect}

{'─' * 50}
TRIGGERING SENSORS
{'─' * 50}
{sensor_ids}

{'=' * 50}
This dispatch was generated automatically by the Network AI Orchestrator.
"""

    logger.info(
        "Field dispatch executed: %s → %s at (%s, %s)",
        dispatch_id, engineer_name,
        destination_latitude, destination_longitude,
    )

    result = {
        "status": "dispatched",
        "dispatch_id": dispatch_id,
        "dispatch_time": dispatch_time,
        "engineer": {
            "name": engineer_name,
            "email": engineer_email,
            "phone": engineer_phone,
        },
        "destination": {
            "description": destination_description,
            "latitude": destination_latitude,
            "longitude": destination_longitude,
            "maps_link": maps_link,
        },
        "urgency": urgency,
        "sensor_ids": [s.strip() for s in sensor_ids.split(",")],
        "email_body": email_body,
    }

    return json.dumps(result)
