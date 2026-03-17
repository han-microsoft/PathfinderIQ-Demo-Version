"""Time tool — get current UTC time.

Module role:
    Example of the simplest possible tool: no parameters, returns a string.
    Useful as a template for new tools. The ``@tool`` decorator auto-generates
    the JSON schema from the function signature and docstring.

Dependents:
    Available to agents via scenario.yaml ``tools: [tools.time_tools:get_current_time]``
"""

from agent_framework import tool


@tool
def get_current_time() -> str:
    """Get the current date and time in UTC."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
