"""Observability package — public API.

Module role:
    Single import point for all observability functionality.  Other modules
    import exactly these symbols:

        from app.observability import configure       # main.py calls this once
        from app.observability import traced_tool     # optional decorator for tools
        from app.observability import get_tracer      # manual span creation
        from app.observability import get_meter       # manual metric recording

    All internals (``_bootstrap``, ``_logging``, ``_middleware``, ``_tracing``,
    ``_metrics``) are private — no external code should import them directly.

Key collaborators:
    - ``_bootstrap.py``  — ``configure()`` entry point
    - ``_tracing.py``    — ``traced_tool`` decorator, ``get_tracer`` helper
    - ``_metrics.py``    — ``get_meter`` helper

Dependents:
    Imported by: ``app.main`` (configure), tool modules (traced_tool, Phase 3)
"""

from app.observability._bootstrap import configure, shutdown_observability
from app.observability._tracing import traced_tool, get_tracer
from app.observability._metrics import get_meter

__all__ = ["configure", "shutdown_observability", "traced_tool", "get_tracer", "get_meter"]
