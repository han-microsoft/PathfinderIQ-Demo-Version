"""SDK middleware wrappers (K8) — tool tracing via the MAF adapter.

Module role:
    Exposes ``create_middleware()`` — the agent runtime calls this to obtain the
    SDK middleware pipeline. The concrete ``FunctionMiddleware`` subclass lives
    in ``agentkit.sdk.maf_client`` (isolate-SDK-quirks); this module is the
    SDK-agnostic entry point the runtime depends on.

Layering:
    Imports ``agentkit.sdk.maf_client`` lazily at call time. No GridIQ
    package, no SDK at import time. Was ``agent/middleware.py``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def create_middleware() -> list:
    """Create the middleware pipeline for agents.

    Returns:
        List of middleware instances. Empty list if the SDK is unavailable.
        Currently contains the tool-tracing middleware only.
    """
    from agentkit.sdk.maf_client import build_tracing_middleware

    return build_tracing_middleware()
