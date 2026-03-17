"""Present structured decision options to the operator with clickable buttons.

Module role:
    Allows the orchestrator to present 2-5 options as structured data
    instead of free-text markdown. The frontend renders these as clickable
    buttons — clicking one sends the selection as a user message.

    Uses flat string fields (not list[dict]) because the Agent Framework
    SDK's function calling reliably populates individual string parameters
    but struggles with complex nested structures like list[dict].

Key collaborators:
    - Frontend: tool-renderers/OptionsCard.tsx renders the buttons
    - Orchestrator agent: calls this when dispatch/remediation is ambiguous

Dependents:
    Imported by: agents (AgentRegistry) via importlib from scenario.yaml
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field


@tool(approval_mode="never_require")
async def present_options(
    prompt: Annotated[
        str,
        Field(description="The question to ask the operator, e.g. 'Which dispatch option do you prefer?'"),
    ],
    option_1_title: Annotated[
        str,
        Field(description="One-line title for option 1, e.g. 'Single dispatch to Goulburn'"),
    ],
    option_1_detail: Annotated[
        str,
        Field(description="Actions, justification, and risks for option 1. Include all three."),
    ],
    option_2_title: Annotated[
        str,
        Field(description="One-line title for option 2"),
    ],
    option_2_detail: Annotated[
        str,
        Field(description="Actions, justification, and risks for option 2"),
    ],
    option_3_title: Annotated[
        str,
        Field(default="", description="One-line title for option 3 (optional, leave empty if only 2 options)"),
    ] = "",
    option_3_detail: Annotated[
        str,
        Field(default="", description="Actions, justification, and risks for option 3 (optional)"),
    ] = "",
    recommended: Annotated[
        int,
        Field(default=0, description="Which option number you recommend (1, 2, or 3). 0 = no recommendation."),
    ] = 0,
    **kwargs: Any,
) -> str:
    """Present structured decision options to the operator.

    The frontend renders these as clickable buttons. The operator clicks
    one, which sends the option title as a chat message. The orchestrator
    then executes the selected option.

    IMPORTANT: After this tool returns, STOP generating. Do not write
    any additional text. Wait for the operator to select an option.
    """
    options = []
    for i, (title, detail) in enumerate([
        (option_1_title, option_1_detail),
        (option_2_title, option_2_detail),
        (option_3_title, option_3_detail),
    ], start=1):
        if not title:
            continue
        options.append({
            "id": i,
            "title": title,
            "detail": detail,
            "recommended": i == recommended,
        })

    return json.dumps({
        "type": "options",
        "prompt": prompt,
        "options": options,
        "_instruction": "Options presented to operator. STOP generating now. Wait for their selection.",
    })
