"""agentkit.config — settings base + per-request scope carrier.

Public surface re-exported here so consumers import from the package, not the
submodule: ``from agentkit.config import BaseAgentSettings, get_settings``.

Modules:
    - ``settings`` — ``BaseAgentSettings`` (generic, domain-blind settings base),
      ``running_in_azure()``, ``get_settings()`` / ``configure_settings()``.
    - ``request_scope`` — frozen per-request scope carrier (lands increment 4).
"""

from agentkit.config.settings import (
    BaseAgentSettings,
    running_in_azure,
    get_settings,
    configure_settings,
)
from agentkit.config.request_scope import (
    RequestScope,
    configure_scope_fallback,
    get_request_scope,
    set_request_scope,
    reset_request_scope,
    get_session_id,
    set_session_id,
    reset_session_id,
)

__all__ = [
    "BaseAgentSettings",
    "running_in_azure",
    "get_settings",
    "configure_settings",
    "RequestScope",
    "configure_scope_fallback",
    "get_request_scope",
    "set_request_scope",
    "reset_request_scope",
    "get_session_id",
    "set_session_id",
    "reset_session_id",
]
