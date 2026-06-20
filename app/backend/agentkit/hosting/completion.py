"""Completion-check helpers for agent runs.

Module role:
    SDK-agnostic, domain-blind pure functions governing the bounded
    post-run completion-check pass: build the hidden follow-up prompt,
    detect a tool-call attempt during the check, decide whether the check
    is satisfied, and produce a fallback for tokenless completions. Lifted
    from GridIQ's ``hosting/fastapi/runtime/_completion_helpers.py``
    (Inc13b).

Design rationale:
    These helpers do not depend on service state. The update is duck-typed
    (``Any`` exposing ``.contents`` items with a ``.type`` attribute) so
    this module imports no SDK.

Layer rule:
    ``agentkit.contracts`` only. Zero SDK / consumer / domain import.
"""

from __future__ import annotations

from typing import Any

from agentkit.contracts.models import StreamEvent, StreamEventType


COMPLETION_CHECK_SENTINEL = "__TASK_COMPLETE__"


def build_completion_check_prompt(prompt: str) -> str:
    """Return the hidden follow-up prompt used after a normal run completes.

    Parameters:
        prompt: Original user request for the active turn.

    Returns:
        The bounded internal instruction that forces one explicit completion
        decision without allowing new tool execution.
    """
    return (
        "[INTERNAL COMPLETION CHECK]\n"
        "Re-evaluate the original user task using the existing conversation and tool results.\n"
        f"Original task:\n{prompt}\n\n"
        f"If the original task is fully complete and no further user-visible output is required, reply with exactly {COMPLETION_CHECK_SENTINEL} and nothing else.\n"
        "Do not call any tools, do not delegate, and do not request additional data during this check. Use only the existing conversation and prior tool results.\n"
        "If the task is not complete, continue from the current state without restarting, reuse prior results, and finish the original task now.\n"
        "Do not repeat the existing answer unless additional content is required to complete the task."
    )


def completion_check_requested_tools(update: Any) -> bool:
    """Return ``True`` when a completion-check update attempts any tool call."""
    return any(
        getattr(content, "type", "") == "function_call"
        for content in (getattr(update, "contents", None) or [])
    )


def is_completion_check_satisfied(
    completion_text: str,
    buffered_events: list[StreamEvent],
) -> bool:
    """Return ``True`` when the completion-check pass says no further work is needed."""
    if completion_text.strip() != COMPLETION_CHECK_SENTINEL:
        return False

    return all(event.event == StreamEventType.TOKEN for event in buffered_events)


def build_empty_completion_fallback(*, tool_call_count: int) -> str:
    """Return the user-visible fallback for tokenless agent completions."""
    if tool_call_count > 0:
        return (
            "I completed the tool loop without producing a final written "
            "answer. The run exhausted its tool budget before it could synthesize "
            "a response. Please retry with a narrower question or reduce the scope "
            "of the request."
        )

    return (
        "I could not produce a final written answer for this request. Please retry."
    )


__all__ = [
    "COMPLETION_CHECK_SENTINEL",
    "build_completion_check_prompt",
    "completion_check_requested_tools",
    "is_completion_check_satisfied",
    "build_empty_completion_fallback",
]
