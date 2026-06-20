"""agentkit.app — the composition-root facade (Tier-1 extraction increment 9).

The capstone of the GridIQ → agentkit extraction. ``AgentApp`` is the one class
that turns the parts shipped by increments 1–8 (config loader, registry,
builder, tool resolver, prompt loader, streaming spine, session store) into the
project goal: *stand up a configured streaming agent, add tools, in a few lines.*

Public surface:
    - ``AgentApp`` — facade. ``.chat()`` (core run path), ``.router()``
      (mountable FastAPI ``APIRouter`` — needs the ``[fastapi]`` extra),
      ``.serve()`` (uvicorn quickstart).
    - ``create_app`` — the quickstart one-liner over ``AgentApp`` (default
      settings via ``BaseAgentSettings.from_env`` + ``tools_prefix``
      normalisation for the fail-closed allowlist).

Layer rule:
    Imports ``agentkit.*`` only — zero consumer (GridIQ) packages, and no hard
    import of ``agent_framework`` / ``fastapi`` / ``uvicorn`` at module load
    (those are injected or lazily imported inside ``.router()`` / ``.serve()``).
"""

from agentkit.app.agent_app import AgentApp
from agentkit.app.quickstart import create_app

__all__ = ["AgentApp", "create_app"]
