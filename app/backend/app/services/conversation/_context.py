"""Context assembly — token counting and sliding-window trimming.

Module role:
    Ensures the conversation history sent to the LLM stays within the token
    budget. Uses tiktoken for accurate token counting with OpenAI-compatible
    models. This module is called before every LLM invocation to trim the
    conversation to fit within ``max_context_tokens - max_response_tokens``.

Trimming strategy:
    1. System prompt is always included (non-negotiable).
    2. The most recent user message is always included.
    3. Remaining budget is filled with messages from newest → oldest.
    4. If a message doesn't fit, it and all older messages are dropped.
    This preserves recency while respecting hard token limits.

Role in system:
    Part of the ``conversation`` service package — the first extracted
    concern from the monolithic router_chat.py. This module owns
    token-budget enforcement for LLM context windows.

Key collaborators:
    - ``app.config.settings``  – provides max_context_tokens, max_response_tokens, llm_model
    - ``app.models.Message``   – input message objects with role, content, tool_calls

Dependents:
    - ``app.services.conversation.__init__`` – re-exports public API
    - ``app.services.context_manager``       – backward-compat re-export shim
    - ``app.routers.chat``                  – builds context before LLM calls
"""

from __future__ import annotations

import logging

from app.foundation.config import settings
from app.foundation.models import Message, Role

# Module logger — structured logs emitted on every context build
logger = logging.getLogger(__name__)

import tiktoken

# Initialise the tokenizer once at import time. Falls back to cl100k_base
# (GPT-4 / GPT-3.5 family) if the model name isn't recognized by tiktoken.
try:
    _encoder = tiktoken.encoding_for_model(settings.llm_model)
except KeyError:
    _encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken.

    Args:
        text: The input string to tokenize.

    Returns:
        Number of tokens (non-negative integer). Empty string returns 0.

    Side effects:
        None — pure function.

    Dependencies:
        Uses the module-level ``_encoder`` (tiktoken) instance.
    """
    return len(_encoder.encode(text))


def _message_tokens(msg: Message) -> int:
    """Estimate tokens for a single message including role overhead.

    Every chat-completion message has ~4 tokens of framing (role separator,
    content delimiter, etc.). Tool calls add their name and serialized
    arguments to the token count.

    Args:
        msg: A Message object from the conversation history.

    Returns:
        Estimated token count for this message.

    Dependencies:
        Calls ``count_tokens()`` for content and tool-call serialization.
    """
    # 4 tokens overhead per message (role, separators, framing)
    overhead = 4
    content_tokens = count_tokens(msg.content) if msg.content else 0
    # Sum tokens across all tool calls (name + serialized arguments)
    tool_tokens = sum(
        count_tokens(tc.name) + count_tokens(str(tc.arguments))
        for tc in msg.tool_calls
    )
    return overhead + content_tokens + tool_tokens


def build_context_window(
    messages: list[Message],
    system_prompt: str | None = None,
    max_turns: int | None = None,
) -> tuple[list[dict], int]:
    """Build the messages array for the LLM API call.

    Returns a tuple of (context_window, tokens_used). The context window is
    a list of dicts in OpenAI chat-completion format, trimmed to fit within
    ``settings.max_context_tokens - settings.max_response_tokens``.
    ``tokens_used`` is the total token count consumed by the returned messages.

    Args:
        messages: Full conversation history (chronological order).
            Caller is responsible for passing only the target agent's
            thread messages (excluding the system prompt message 0).
        system_prompt: Override system prompt. Falls back to settings.
        max_turns: Maximum number of user+assistant turn pairs to include.
            None = unlimited (token budget governs). When set to a positive
            integer, messages are pre-sliced to keep only the last N turns
            before token-budget trimming applies.

    Returns:
        Tuple of (context_window, tokens_used). context_window is a list of
        message dicts ready for the LLM API. tokens_used is the total token
        count consumed by those messages.

    Side effects:
        Emits a structured log (``conversation.context_built``) with
        token utilization metrics on every call.

    Dependencies:
        - ``settings.max_context_tokens`` — hard token limit for the model
        - ``settings.max_response_tokens`` — reserved for the response
        - ``settings.system_prompt`` — default system prompt if none given
    """
    prompt = system_prompt or settings.system_prompt
    budget = settings.max_context_tokens - settings.max_response_tokens
    # Track the total budget before any deductions for logging
    total_budget = budget

    # Pre-slice by max_turns: keep only the last N turn pairs (user+assistant).
    # Each turn = 2 messages (user + assistant), so keep last max_turns * 2.
    # This provides coarse context depth control before token-budget trimming.
    if max_turns is not None and max_turns > 0:
        slice_count = max_turns * 2
        if len(messages) > slice_count:
            messages = messages[-slice_count:]

    # System message is always first and always included
    system_msg = {"role": "system", "content": prompt}
    budget -= count_tokens(prompt) + 4  # 4 tokens overhead for system message

    if budget <= 0:
        # System prompt alone exceeds the budget — return only the system
        # message. This is a degenerate case but must not crash.
        logger.warning(
            "conversation.context_built",
            extra={
                "messages_total": len(messages),
                "messages_kept": 0,
                "messages_dropped": len(messages),
                "tokens_used": total_budget - budget,
                "tokens_budget": total_budget,
                "budget_exhausted_by_system_prompt": True,
            },
        )
        return [system_msg], total_budget - budget

    # Convert messages to dicts, newest first for priority filling.
    # Iterating in reverse ensures the most recent messages get budget
    # priority; we stop as soon as a message doesn't fit.
    formatted: list[dict] = []
    for msg in reversed(messages):
        msg_dict = {"role": msg.role.value, "content": msg.content}
        # Attach tool calls if present (function-calling format)
        if msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": str(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
        # Tool-result messages need a tool_call_id reference.
        # Skip tool messages with no valid tool_call_id — the OpenAI API
        # rejects tool-role messages with an empty tool_call_id (400 error).
        if msg.role == Role.TOOL:
            if msg.tool_calls and msg.tool_calls[0].id:
                msg_dict["tool_call_id"] = msg.tool_calls[0].id
            else:
                logger.warning(
                    "conversation.context.orphaned_tool_message",
                    extra={"message_id": msg.id},
                )
                continue  # Skip this message — no valid tool_call_id

        tokens = _message_tokens(msg)
        if tokens > budget:
            break  # Can't fit this message — stop including older ones
        budget -= tokens
        formatted.append(msg_dict)

    # Reverse back to chronological order
    formatted.reverse()

    # Compute observability metrics
    messages_kept = len(formatted)
    messages_dropped = len(messages) - messages_kept
    tokens_used = total_budget - budget

    # Structured log emitted on every context build for observability.
    # Enables dashboards tracking token utilization and message trimming.
    logger.info(
        "conversation.context_built",
        extra={
            "messages_total": len(messages),
            "messages_kept": messages_kept,
            "messages_dropped": messages_dropped,
            "tokens_used": tokens_used,
            "tokens_budget": total_budget,
        },
    )

    # Record OTel metrics for context window utilization
    from app.services.conversation._tracing import record_context_utilization
    record_context_utilization(
        tokens_used=tokens_used,
        tokens_budget=total_budget,
        messages_dropped=messages_dropped,
    )

    return [system_msg, *formatted], tokens_used


def build_context_snapshot(
    context_window: list[dict],
    *,
    tokens_used: int = 0,
    agent_session_id: str = "",
    agent_id: str = "",
    messages_total: int = 0,
    max_turns: int | None = None,
    user_message: str = "",
) -> dict:
    """Build a JSON-serializable snapshot of the context sent to the LLM.

    Captures exactly what was sent so the ContextInspector can display it.
    Called after ``build_context_window`` with the resulting context array.

    Args:
        context_window: The message dicts returned by build_context_window.
        agent_session_id: The agent's SDK thread identifier.
        agent_id: Config key of the agent (e.g. "orchestrator").
        messages_total: Total messages in the thread before any trimming.
        max_turns: The max_turns setting used for this call.
        user_message: The user query this response answers.

    Returns:
        Dict with snapshot fields matching the ContextSnapshot model.

    Side effects:
        None — pure function.
    """
    # Extract system prompt from the first message if present
    system_prompt_chars = 0
    if context_window and context_window[0].get("role") == "system":
        system_prompt_chars = len(context_window[0].get("content", ""))

    # Messages kept = all context items minus the system message
    messages_kept = len(context_window) - (1 if system_prompt_chars > 0 else 0)
    messages_dropped = messages_total - messages_kept

    # Use pre-computed tokens_used if provided (from build_context_window).
    # Fall back to re-tokenizing for direct callers that don't pass it.
    if tokens_used <= 0:
        tokens_used = sum(
            count_tokens(m.get("content", "")) + 4  # 4 tokens overhead per message
            for m in context_window
        )
    tokens_budget = settings.max_context_tokens - settings.max_response_tokens

    return {
        "agent_session_id": agent_session_id,
        "agent_id": agent_id,
        "system_prompt_chars": system_prompt_chars,
        "messages_total": messages_total,
        "messages_kept": messages_kept,
        "messages_dropped": max(0, messages_dropped),
        "tokens_used": tokens_used,
        "tokens_budget": tokens_budget,
        "max_turns": max_turns,
        "user_message": user_message,
        "context_messages": [
            {"role": m.get("role", ""), "content": m.get("content", "")}
            for m in context_window
        ],
    }
