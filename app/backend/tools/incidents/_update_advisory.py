"""update_advisory — post a customer-facing service advisory (spoofed).

Module role:
    Spoofed incident management tool. Simulates posting a customer-facing
    service advisory. Returns realistic JSON confirming distribution.

Key collaborators:
    - tools._spoof_state.post_advisory — writes advisory to spoof state
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
@traced_tool("update_advisory", backend="spoof")
async def update_advisory(
    advisory_text: Annotated[str, Field(
        description="Customer-facing advisory text.",
    )],
    affected_regions: Annotated[str, Field(
        description="Affected geographic regions (e.g., 'Sydney, Melbourne').",
    )],
    estimated_resolution: Annotated[str, Field(
        description="Estimated time to resolution.",
    )] = "",
    **kwargs: Any,
) -> str:
    """Post a customer-facing service advisory (spoofed).

    Generates a timestamped advisory ID and records the advisory in
    session-scoped spoof state. Returns JSON confirming distribution.

    Args:
        advisory_text: The advisory message text.
        affected_regions: Geographic regions affected.
        estimated_resolution: Estimated resolution time.

    Returns:
        JSON string with advisory_id, status, and distribution count.

    Side effects:
        Writes to spoof state via post_advisory().
    """
    # Import lazily to avoid circular deps at module load time
    from app.foundation.request_context import get_session_id
    from tools._spoof_state import post_advisory

    sid = get_session_id()
    # Generate a timestamped advisory ID
    adv_id = f"ADV-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    result = post_advisory(
        sid, adv_id,
        text=advisory_text,
        regions=affected_regions,
        resolution=estimated_resolution,
    )

    logger.info(
        "tool.update_advisory.executed",
        extra={"session_id": sid, "advisory_id": adv_id},
    )

    return json.dumps({
        "advisory_id": adv_id,
        "status": "posted",
        "distribution_count": 847,
        **result,
    })
