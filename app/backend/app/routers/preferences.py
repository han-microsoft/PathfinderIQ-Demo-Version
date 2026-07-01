"""Preferences router — per-user runtime scenario selection.

Endpoints:
    GET /api/preferences  — the current user's scenario-only preferences.

The companion write path lives on the scenarios router
(``POST /api/scenarios/select``) so the swap verb sits beside the catalog.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.auth import User
from app.deps import get_current_user
from app.services.preferences import get_preferences_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(request: Request, user: User = Depends(get_current_user)):
    """Return the current user's scenario-only preferences."""
    return get_preferences_store(request).get(user.oid)
