"""Last-run metadata for the agent service — read by observability router.

Module role:
    Holds a module-level dict tracking the most recent agent run's metadata
    (model, tokens, duration, tool calls, thread ID). Updated by the agent
    service after each run. Read by the observability router's /status endpoint.

    This module exists to enforce the layer boundary: services write here,
    routers read from here. Services never import from routers.

Key collaborators:
    - app.services.llm.agent — calls update_last_run() after each run
    - app.routers.observability — calls get_last_run() for /status endpoint

Dependents:
    Called by: app.services.llm.agent (write), app.routers.observability (read)
"""

from __future__ import annotations

# Module-level last-run metadata — updated after each agent run.
# NOT connected to chatStore or session state — purely backend-side
# operational metadata for the observability panel.
_last_run: dict = {
    "model": "",
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "duration_ms": 0,
    "tool_calls": 0,
    "thread_id": "",
}


def update_last_run(**kwargs: object) -> None:
    """Update last-run metadata snapshot (called by agent service after each run).

    Args:
        **kwargs: Key-value pairs to merge into the _last_run dict.
                  Valid keys: model, input_tokens, output_tokens,
                  total_tokens, duration_ms, tool_calls, thread_id.

    Side effects:
        Mutates module-level ``_last_run`` dict.

    Dependents:
        Called by: app.services.llm.agent (after stream_completion completes)
    """
    _last_run.update(kwargs)


def get_last_run() -> dict:
    """Return a copy of the last-run metadata.

    Returns a copy so callers cannot accidentally mutate the internal state.

    Returns:
        Dict with keys: model, input_tokens, output_tokens, total_tokens,
        duration_ms, tool_calls, thread_id.

    Dependents:
        Called by: app.routers.observability (GET /api/observability/status)
    """
    return dict(_last_run)
