"""Auth setup router — MSAL configuration for the frontend.

Module role:
    Provides the ``/api/auth_setup`` endpoint that the frontend calls before
    login to determine whether to show the login screen and what MSAL
    configuration to use.

    This endpoint is UNAUTHENTICATED — it must be callable without a token
    because the frontend needs the config to acquire a token in the first place.

Key collaborators:
    - app.config.settings — reads auth_enabled, auth_client_id, auth_tenant_id

Dependents:
    Called by: frontend ``authConfig.ts`` on page load
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.foundation.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.get("/auth_setup")
async def auth_setup():
    """Return MSAL configuration to the frontend.

    Unauthenticated — called before login to decide whether to show
    the login screen. When AUTH_ENABLED=false, returns useLogin=false
    and the frontend skips MSAL initialization entirely.

    Returns:
        dict: {useLogin: bool, clientId?: str, authority?: str, scopes?: list[str]}

    Side effects:
        Structured log: auth.setup_requested
    """
    logger.info(
        "auth.setup_requested",
        extra={
            "use_login": settings.auth_enabled,
            "tenant_id": settings.auth_tenant_id if settings.auth_enabled else "",
        },
    )
    if not settings.auth_enabled:
        return {"useLogin": False}
    return {
        "useLogin": True,
        "clientId": settings.auth_client_id,
        "authority": f"https://login.microsoftonline.com/{settings.auth_tenant_id}",
        "scopes": [f"api://{settings.auth_client_id}/access_as_user"],
    }
