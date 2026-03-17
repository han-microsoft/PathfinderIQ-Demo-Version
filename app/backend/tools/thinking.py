"""thinking — structured reasoning tool for agents.

Module role:
    Gives agents a dedicated tool to write down their reasoning about the
    current situation, clarify motivations, and plan next actions. The tool
    is a no-op — it accepts the agent's thoughts and returns a confirmation.
    The value is in the arguments (rendered in the UI), not the result.

Key collaborators:
    - ``agent_framework.tool`` — ``@tool`` decorator for JSON schema generation
    - Orchestrator agent — calls this before handoffs or dispatch decisions

Dependents:
    Imported by: ``agents`` (AgentRegistry) via scenario.yaml tool spec
    ``tools.thinking:thinking``
"""

from typing import Annotated

from agent_framework import tool
from pydantic import Field


@tool(approval_mode="never_require")
async def thinking(
    thoughts: Annotated[str, Field(
        description=(
            "Your reasoning about the current situation: what you know, "
            "what you've ruled out, what remains uncertain, and what your "
            "next action will be and why."
        ),
    )],
) -> str:
    """Write down your current reasoning and next planned action."""
    return "Acknowledged."
