"""Single-agent NOC investigation service via YAML-driven agent loader.

Module role:
    Implements the LLMService protocol using the Microsoft Agent Framework SDK.
    Instead of sending raw LLM completions, this service builds a fully-equipped
    agent (with tools, prompts, and session memory) from the active scenario’s
    ``scenario.yaml`` and streams its responses as SSE events.

Agent lifecycle (per request):
    1. Load scenario.yaml → resolve tools + prompts via agents (AgentRegistry)
    2. Build agent via ``client.as_agent(name, description, instructions, tools)``
    3. Get or create AgentSession (maps UI session_id → thread)
    4. Run ``agent.run(user_message, stream=True, session=session)``
    5. Map AgentResponseUpdate objects to StreamEvent yields

Architectural note:
    The agent is rebuilt per request to avoid the SDK’s "already running"
    restriction. The AgentSession persists conversation thread across calls.

Configuration (all in control/.env):
    LLM_PROVIDER=agent
    AZURE_AI_PROJECT_ENDPOINT=<Azure AI Foundry endpoint>
    AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=<model deployment>
    FABRIC_*  — for graph/telemetry tools
    AI_SEARCH_* — for runbook/ticket search tools

Auth: DefaultAzureCredential (``az login`` or managed identity). No API keys.

Key collaborators:
    - ``agent_framework.azure.AzureAIAgentClient`` – Azure AI Agents API client
    - ``agents.registry.build()``                – scenario-driven agent builder
    - ``app.models.StreamEvent``                    – yield type for SSE streaming

Dependents:
    Created by: ``llm.py:create_llm_service()`` when ``LLM_PROVIDER=agent``
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agent_framework import AgentResponseUpdate

from app.foundation.config import settings
from app.foundation.models import StreamEvent, StreamEventType, StreamMetadata

logger = logging.getLogger(__name__)


# ── Context injection helpers (moved from deleted _thread_sync.py) ───────────


def _filter_prior_messages(messages: list[dict]) -> list[dict]:
    """Filter messages to only prior conversation (exclude current query).

    Keeps user, assistant, and tool messages. Removes the last user
    message (which is the current query being sent to the agent).

    Args:
        messages: Full message list in OpenAI chat-completion format.

    Returns:
        List of prior messages (excluding system and current user query).
    """
    prior = [
        m for m in messages
        if m.get("role") in ("user", "assistant", "tool")
    ]
    # Remove the last user message (that's the current query)
    if prior and prior[-1].get("role") == "user":
        prior = prior[:-1]
    return prior


def _build_context_injection(
    prior_messages: list[dict],
    user_message: str,
    messages_dropped: int = 0,
) -> str:
    """Build the <prior_conversation> context block + user message.

    Constructs a structured conversation transcript from prior messages
    and prepends it to the current user message. This gives the LLM
    full conversation context when the SDK thread has no history.

    Args:
        prior_messages: Prior conversation messages (already filtered).
        user_message: The current user query text.
        messages_dropped: Number of messages trimmed by the context window.

    Returns:
        The augmented user message with prior conversation block prepended.
    """
    context_lines: list[str] = []

    # If the context window trimmed older messages, notify the agent
    if messages_dropped > 0:
        context_lines.append(
            f"[Note: {messages_dropped} earlier messages were trimmed from context. "
            f"You are seeing the most recent messages only. "
            f"If you need information from earlier in the conversation, ask the user.]"
        )

    for m in prior_messages:
        role = m.get("role", "unknown").upper()
        content = m.get("content", "")
        tool_calls = m.get("tool_calls", [])
        tool_summary = ""
        if tool_calls:
            tool_details = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    tool_details.append("?")
                    continue
                name = tc.get("function", {}).get("name", tc.get("name", "?"))
                args_raw = tc.get("function", {}).get("arguments", "")
                if isinstance(args_raw, dict):
                    import json as _json
                    args_raw = _json.dumps(args_raw, default=str)
                if isinstance(args_raw, str) and len(args_raw) > 300:
                    args_raw = args_raw[:300] + "..."
                tool_details.append(f"{name}({args_raw})")
            tool_summary = f" [tools: {'; '.join(tool_details)}]"
        if content:
            # Tool-bearing messages contain analysis of tool results — preserve more
            limit = 4000 if tool_calls else 2000
            truncated = content[:limit] + ("..." if len(content) > limit else "")
            context_lines.append(f"{role}{tool_summary}: {truncated}")
        elif tool_summary:
            context_lines.append(f"{role}{tool_summary}: (tool results only)")

    if not context_lines:
        return user_message

    context_block = "\n".join(context_lines)
    augmented = (
        f"<prior_conversation>\n"
        f"The following is the conversation history from this session. "
        f"Use it as context for the current question.\n\n"
        f"{context_block}\n"
        f"</prior_conversation>\n\n"
        f"{user_message}"
    )

    logger.info(
        "conversation.context_injected",
        extra={
            "prior_message_count": len(prior_messages),
            "context_length": len(context_block),
        },
    )

    return augmented


from app.foundation.retry import (
    is_rate_limit, parse_retry_seconds, should_retry,
    log_retry, get_model_fallback_queue,
)


def _is_rate_limit(exc: Exception) -> bool:
    """Backward compat — delegates to shared retry module."""
    return is_rate_limit(exc)


from app.services.llm._event_mapping import (
    map_update_to_events as _map_update_to_events_fn,
    extract_usage as _extract_usage,
    extract_user_message as _extract_user_message,
)


# ── Service ──────────────────────────────────────────────────────────────────


class AgentFrameworkService:
    """LLMService backed by the Azure AI Agent Framework.

    The agent is built from the active scenario's YAML config. Specialists
    are delegated to via the ``delegate_to_agent`` tool call pattern.
    Agent is rebuilt per request to avoid SDK \"already running\" restrictions.

    Key collaborators:
        - ``agents.registry.build()`` — builds agent from scenario.yaml
        - ``_filter_prior_messages()``    — prior conversation extraction
        - ``_build_context_injection()``     — context injection for restart recovery
        - ``_map_update_to_events()``    — SDK update → SSE event transform
        - ``_inject_orphan_context()``   — prior conversation injection
    """

    def __init__(self) -> None:
        import os

        from app.foundation.credentials import get_azure_credential

        # Pick credential — managed identity in cloud, CLI locally
        credential = get_azure_credential(require_fabric_sp=False)

        # Capture env vars for the client factory closure
        project_endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
        model_deployment = os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"]

        # Function invocation config — applied to each new client
        func_invocation_config = {
            "enabled": True,
            "max_iterations": 40,
            "max_consecutive_errors_per_request": 3,
            "terminate_on_unknown_calls": False,
            "additional_tools": [],
            "include_detailed_errors": True,
        }

        def _create_client():
            """Create a fresh AzureAIAgentClient.

            Each agent gets its own client instance to prevent identity bleed.
            The SDK client holds mutable state (agent_name, agent_id,
            _agent_definition) that persists across as_agent() calls — sharing
            a single client between agents causes the first agent's identity
            to leak into subsequent agents.
            """
            from agent_framework.azure import AzureAIAgentClient

            client = AzureAIAgentClient(
                project_endpoint=project_endpoint,
                model_deployment_name=model_deployment,
                credential=credential,
            )
            client.function_invocation_configuration = dict(func_invocation_config)
            return client

        # Register the client factory with the agent registry.
        # The registry creates and caches one client per agent_id.
        from agents import registry as _agent_registry
        _agent_registry.configure(_create_client)

        # Resolve control directory for agent loading
        self._control_dir = Path(__file__).resolve().parents[4] / "control"

        # Agent build cache — avoids rebuilding the same agent+model on every
        # request. Keyed by (agent_id, model). Invalidated implicitly when
        # scenario changes (process restart).
        self._agent_cache: dict[tuple[str, str], Any] = {}

        logger.info("Agent service initialised (per-agent client isolation enabled)")

    # ── Static helpers (no instance state, independently testable) ───────

    @staticmethod
    def _map_update_to_events(
        update: AgentResponseUpdate,
        usage: dict[str, int],
    ) -> list[StreamEvent]:
        """Delegate to module-level function in _event_mapping.py."""
        return _map_update_to_events_fn(update, usage)

    # ── Core streaming method ────────────────────────────────────────────

    async def stream_completion(
        self,
        messages: list[dict],
        *,
        abort_event: asyncio.Event | None = None,
        session_id: str = "",
        agent_id: str = "",
        messages_dropped: int = 0,
    ) -> AsyncIterator[StreamEvent]:
        """Run the agent and stream SSE events.

        Phases:
            1. Extract user message from context window
            2. Create fresh SDK session + inject prior context
            3. Run agent with rate-limit retry, mapping updates to SSE events
            4. Emit metadata and terminal DONE event

        Args:
            messages: OpenAI-format message dicts from the context window.
            abort_event: Set by the abort endpoint to cancel generation.
            session_id: UI session identifier for thread synchronisation.
            agent_id: Agent config key — passed to load_agent to build the
                correct agent with the right tools and SDK-level instructions.

        Yields:
            StreamEvent objects for the SSE transport layer.

        Dependents:
            Called by: routers/chat.py via LLMService protocol.
        """
        start = time.monotonic()
        assistant_id = uuid.uuid4().hex

        # Phase 1: Extract user message
        user_message = _extract_user_message(messages)
        if not user_message:
            yield StreamEvent(
                event=StreamEventType.ERROR,
                data={"error": "No user message found"},
            )
            return

        # Phase 2: Fresh SDK session per request.
        # A new AgentSession is created for every request to eliminate
        # Foundry server-side thread memory that leaked cross-agent context.
        # Our context window (built by SessionStateManager) is the sole
        # source of truth — the SDK session carries no prior history.
        from agent_framework import AgentSession
        session = AgentSession()

        # Inject prior conversation context into the user message.
        # The SDK agent only accepts a single string — it doesn't consume
        # our messages array. We inject from the clean, isolated context
        # window (already scoped to this agent's thread by SSM).
        prior_messages = _filter_prior_messages(messages)
        if prior_messages:
            user_message = _build_context_injection(
                prior_messages, user_message,
                messages_dropped=messages_dropped,
            )
            logger.info(
                "agent.context_injected: agent_id=%s, prior_msgs=%d",
                agent_id or "(default)", len(prior_messages),
            )

        # Phase 3: Agent run with model fallback + retry
        tool_call_count = 0
        usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}
        max_retries = 4
        model_queue = get_model_fallback_queue()
        _completed = False

        for model_idx, current_model in enumerate(model_queue):
          if _completed:
              break

          for attempt in range(max_retries + 1):
            try:
                from agents import registry as _agent_registry

                # Cache agent builds by (agent_id, model, language) to avoid
                # rebuilding on every request. Language is included because the
                # prompt suffix changes per language (see _prompts.py).
                from app.foundation.request_context import get_language as _get_lang
                _cache_key = (agent_id or "default", current_model, _get_lang())
                if _cache_key in self._agent_cache:
                    agent = self._agent_cache[_cache_key]
                else:
                    agent = _agent_registry.build(agent_id or None, model_override=current_model)
                    self._agent_cache[_cache_key] = agent

                logger.info(
                    "agent.built: requested_id=%s, agent_name=%s, model=%s",
                    agent_id or "(default)", getattr(agent, "name", "?"), current_model,
                )

                if attempt == 0 and model_idx == 0:
                    logger.info(
                        "agent.run.start: session_id=%s, agent_id=%s, model=%s",
                        session_id, agent_id or "(default)", current_model,
                    )

                async for update in agent.run(user_message, stream=True, session=session):
                    # Check abort before processing each update
                    if abort_event and abort_event.is_set():
                        yield StreamEvent(event=StreamEventType.ABORTED)
                        return

                    # agent.run(stream=True) yields AgentResponseUpdate directly
                    if not isinstance(update, AgentResponseUpdate):
                        continue

                    # Map SDK update to SSE events and yield them
                    sse_events = self._map_update_to_events(update, usage)
                    for sse_event in sse_events:
                        yield sse_event

                    # Count function_call content objects for observability.
                    # Counted at the content level (canonical), not SSE events.
                    tool_call_count += sum(
                        1 for c in (update.contents or [])
                        if getattr(c, "type", "") == "function_call"
                    )

                break  # Successful completion — exit retry loop

            except Exception as exc:
                retry, sleep_secs = should_retry(exc, attempt, max_retries)
                if retry:
                    if is_rate_limit(exc):
                        yield StreamEvent(
                            event=StreamEventType.RATE_LIMITED,
                            data={"retry_after": int(sleep_secs), "attempt": attempt + 1},
                        )
                    log_retry(
                        f"agent({agent_id or 'default'})", attempt, max_retries,
                        exc, sleep_secs, model=current_model,
                    )
                    await asyncio.sleep(sleep_secs)
                    continue
                elif model_idx < len(model_queue) - 1:
                    # Try next model in the fallback queue
                    logger.warning(
                        "agent.model_fallback: %s exhausted, falling back to %s",
                        current_model, model_queue[model_idx + 1],
                    )
                    break  # break inner loop → continue outer with next model
                else:
                    # All models and retries exhausted
                    from app.foundation.errors import classify_error, generate_error_id, make_error_event
                    error_id = generate_error_id()
                    error_code, error_message = classify_error(exc)
                    logger.exception(
                        "agent.run.error [error_id=%s, code=%s, models_tried=%s]: %s",
                        error_id, error_code.value, model_queue, exc,
                    )
                    yield make_error_event(
                        error_code, error_message, error_id=error_id,
                    )
                    return
          else:
              # Inner loop exhausted retries for this model — continue to next
              continue
          _completed = True  # Inner loop broke successfully

        # Phase 4: Metadata + DONE
        elapsed = (time.monotonic() - start) * 1000

        # The model actually used is the last current_model from the retry loop.
        # Per-agent model is defined in scenario.yaml; fallback queue may override it.
        request_model = current_model

        # Log run completion for observability panel (captured by LogBroadcaster)
        logger.info(
            "agent.run.complete: %.1fs total, %d tool calls",
            elapsed / 1000, tool_call_count,
        )

        # Update last-run metadata for /api/observability/status endpoint
        from app.services.agent_run_state import update_last_run
        update_last_run(
            model=request_model,
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            total_tokens=usage["total"],
            duration_ms=round(elapsed),
            tool_calls=tool_call_count,
            thread_id=session.service_session_id or "",
        )

        # Estimate cost for the current model and token counts
        from app.llmops._cost import estimate_cost
        cost = estimate_cost(request_model, usage["input"], usage["output"])

        yield StreamEvent(
            event=StreamEventType.METADATA,
            data=StreamMetadata(
                prompt_tokens=usage["input"],
                completion_tokens=usage["output"],
                total_tokens=usage["total"],
                duration_ms=elapsed,
                model=request_model,
                assistant_message_id=assistant_id,
                estimated_cost_usd=cost,
            ).model_dump(),
        )
        yield StreamEvent(event=StreamEventType.DONE)
