"""call_engineer — function tool that simulates phoning a field engineer.

Module role:
    Simulates placing a phone call to a field engineer. Accepts a name and
    phone number, waits 5 seconds (ring duration), then returns a structured
    JSON payload indicating the engineer didn't pick up. Designed as a demo
    flourish — the frontend renders a Teams-style calling overlay with ring
    tones while the backend sleeps.

Key collaborators:
    - ``agent_framework.tool`` – ``@tool`` decorator for JSON schema generation
    - Orchestrator agent – calls this tool when asked to reach an engineer
    - Frontend ``CallEngineerRenderer`` – renders the calling UI + ring tone

Dependents:
    Imported by: ``tools/dispatch/__init__.py``
"""

import asyncio
import json
import logging
from typing import Annotated

from agent_framework import tool
from pydantic import Field

from app.observability import traced_tool

logger = logging.getLogger(__name__)

# Ring duration in seconds — frontend ring tone is timed to match
_RING_DURATION_SECONDS = 5


@tool
@traced_tool("call_engineer", backend="default")
async def call_engineer(
    engineer_name: Annotated[str, Field(
        description="Full name of the engineer to call.",
    )],
    engineer_phone: Annotated[str, Field(
        description="Phone number of the engineer to call.",
    )],
) -> str:
    """Call a field engineer's phone to reach them directly. Simulates ringing and returns the call outcome."""

    # Simulate the phone ringing for the configured duration
    logger.info(
        "Calling engineer %s at %s — ringing for %ds",
        engineer_name, engineer_phone, _RING_DURATION_SECONDS,
    )
    await asyncio.sleep(_RING_DURATION_SECONDS)

    # Engineer never picks up in the demo — this is the punchline
    logger.info(
        "Call to %s (%s) went unanswered after %ds",
        engineer_name, engineer_phone, _RING_DURATION_SECONDS,
    )

    result = {
        "status": "no_answer",
        "engineer_name": engineer_name,
        "engineer_phone": engineer_phone,
        "ring_duration_seconds": _RING_DURATION_SECONDS,
        "message": "Recipient didn't pick up the phone",
    }

    return json.dumps(result)
