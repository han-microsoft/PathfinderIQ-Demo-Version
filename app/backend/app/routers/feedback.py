"""Bug report router — submit feedback to Cosmos DB.

Module role:
    Provides a single endpoint for users to submit bug reports / feedback.
    Reports are stored in a dedicated ``feedback`` container in the same
    Cosmos DB account used for sessions. The container is auto-created on
    first write if it doesn't exist — no infrastructure reprovisioning needed.

Endpoints:
    POST /api/feedback — Submit a bug report (title, description)

Key collaborators:
    - ``app.config.settings`` — reads cosmos_session_endpoint for Cosmos connection
    - ``app.deps.get_current_user`` — captures submitter identity

Dependents:
    Called by: frontend bug report form in the left sidebar
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_current_user, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

# Lazy-initialized Cosmos container for feedback
_feedback_container = None


class FeedbackRequest(BaseModel):
    """Client → Server: submit a bug report."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=5000)


class FeedbackResponse(BaseModel):
    """Server → Client: confirmation of submission."""

    id: str
    status: str = "submitted"


def _get_feedback_container():
    """Get or create the Cosmos DB feedback container (lazy singleton).

    Auto-creates the ``feedback`` container in the same database as
    sessions. Uses ``/id`` as partition key. No reprovisioning needed.

    Returns:
        A Cosmos ContainerProxy, or None if Cosmos is not configured.

    Side effects:
        Creates the container on first call if it doesn't exist.
    """
    global _feedback_container
    if _feedback_container is not None:
        return _feedback_container

    from app.foundation.config import settings
    if not settings.cosmos_session_endpoint:
        return None

    try:
        from azure.identity import DefaultAzureCredential
        from azure.cosmos import CosmosClient, PartitionKey

        credential = DefaultAzureCredential()
        client = CosmosClient(
            url=settings.cosmos_session_endpoint,
            credential=credential,
        )
        database = client.get_database_client(settings.cosmos_session_database)

        # Create container if it doesn't exist — idempotent
        database.create_container_if_not_exists(
            id="feedback",
            partition_key=PartitionKey(path="/id"),
        )
        _feedback_container = database.get_container_client("feedback")
        logger.info("Feedback container ready (Cosmos DB)")
        return _feedback_container
    except Exception as e:
        logger.warning("Failed to initialize feedback container: %s", e)
        return None


@router.post("", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(
    req: FeedbackRequest,
    user: User = Depends(get_current_user),
):
    """Submit a bug report.

    Stores the report in Cosmos DB with user identity, timestamp, and
    a unique ID. Falls back to logging if Cosmos is unavailable.
    """
    report_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": report_id,
        "type": "feedback",
        "title": req.title,
        "description": req.description,
        "user_oid": user.oid,
        "user_email": user.email,
        "user_name": user.name,
        "submitted_at": now,
        "status": "open",
    }

    container = _get_feedback_container()
    if container:
        try:
            container.create_item(body=doc)
            logger.info(
                "feedback.submitted",
                extra={"report_id": report_id, "user_oid": user.oid},
            )
        except Exception as e:
            logger.error("feedback.submit_failed: %s", e)
            raise HTTPException(
                status_code=503,
                detail="Feedback service temporarily unavailable",
            )
    else:
        # No Cosmos — log the feedback so it's not lost
        logger.info(
            "feedback.submitted_to_log",
            extra={
                "report_id": report_id,
                "title": req.title,
                "description": req.description,
                "user_oid": user.oid,
                "user_email": user.email,
            },
        )

    return FeedbackResponse(id=report_id)
