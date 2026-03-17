"""Session state manager — single authority for thread lifecycle and context.

Module role:
    Owns the invariant: "For session X, agent Y, the thread exists with
    the correct system prompt, and the context window contains only this
    agent's messages." The chat router delegates to this module instead
    of assembling thread/context logic inline.

    This module is stateless — it receives the store and session per call.
    It does not hold references to request-scoped objects.

Responsibilities:
    1. Eagerly initialize all agent threads on session creation
    2. Ensure thread exists with correct system prompt (ensure_thread)
    3. Build token-budgeted context window (build_turn_context)
    4. Produce context snapshot for auditability (build_turn_context)
    5. Signal first-message detection for auto-titling (ensure_thread)
    6. Enforce thread isolation by construction (build_turn_context)

Does NOT own:
    - Message persistence (ConversationTurn + SessionStore)
    - SDK session mapping (agent.py creates fresh AgentSession per request)
    - HTTP transport (chat router)
    - Auto-titling (ConversationTurn uses the is_first_message flag)

Key collaborators:
    - agents.registry.get_prompt — loads prompt text from scenario config
    - _context.build_context_window — token-budgeted sliding window
    - _context.build_context_snapshot — audit snapshot
    - SessionStore — thread creation (via create_thread)

Dependents:
    - routers/chat.py — calls ensure_thread + build_turn_context per request
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.foundation.models import AgentThread, ContextSnapshot, Message, Role, Session
from app.services.conversation._context import build_context_window, build_context_snapshot

if TYPE_CHECKING:
    from app.services.session_store import SessionStore

# Module logger — structured logs emitted on thread creation and prompt backfill
logger = logging.getLogger(__name__)


class SessionStateManager:
    """Single authority for per-agent thread lifecycle and context assembly.

    Stateless — receives the store and session per call. Does not hold
    references to request-scoped objects.

    Lifecycle:
        Created once (or per-request — it's stateless, doesn't matter).
        Called by the chat router before ConversationTurn.start().

    Key collaborators:
        - agents.registry.get_prompt — prompt text resolution
        - agents._config.iter_agents — enumerate all agents
        - _context.build_context_window — token-budgeted context
        - _context.build_context_snapshot — audit snapshot
        - SessionStore.create_thread — thread persistence
    """

    async def initialize_all_threads(
        self,
        session: Session,
        session_id: str,
        store: "SessionStore",
    ) -> None:
        """Eagerly create threads for every agent defined in scenario.yaml.

        Called once at session creation time. Each agent gets its own thread
        with its system prompt as message 0. This eliminates lazy init and
        ensures every agent tab has an isolated, correctly-prompted thread
        from the start — preventing identity bleed between agents.

        Args:
            session: The newly created Session object (mutated in-place).
            session_id: Session identifier.
            store: SessionStore for persistence.

        Side effects:
            - Creates one thread per agent via store.create_thread()
            - Mutates session.threads in-place
            - Emits structured log per thread created
        """
        from agents import registry as _agent_registry
        from agents._config import load_agents_block, iter_agents

        config = load_agents_block()
        entries = iter_agents(config)

        for agent_id, agent_cfg in entries:
            # Skip if thread already exists (e.g. from saved conversation)
            if agent_id in session.threads:
                continue

            _, display_name, prompt_text = _agent_registry.get_prompt(agent_id)

            thread = await store.create_thread(
                session_id, agent_id, display_name, prompt_text
            )
            session.threads[agent_id] = thread

            logger.info(
                "session_state.thread_initialized",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "agent_name": display_name,
                    "prompt_chars": len(prompt_text),
                },
            )

        logger.info(
            "session_state.all_threads_initialized",
            extra={
                "session_id": session_id,
                "thread_count": len(session.threads),
                "agent_ids": list(session.threads.keys()),
            },
        )

    async def ensure_thread(
        self,
        session: Session,
        session_id: str,
        agent_id: str,
        store: SessionStore,
    ) -> tuple[AgentThread, bool]:
        """Ensure the agent's thread exists with the correct system prompt.

        If the thread doesn't exist, creates it via store.create_thread()
        with the system prompt loaded from the agent's scenario config.
        If the thread exists but has no system prompt (bare thread from
        auto-create), backfills the prompt as message 0.

        Args:
            session: The current Session object (mutated in-place if thread created).
            session_id: Session identifier.
            agent_id: Agent config key (e.g. "network_investigator").
                Empty string defaults to "orchestrator".
            store: SessionStore for persistence.

        Returns:
            (thread, is_first_message) — the thread and whether this will
            be the first conversational (non-system) message in the thread.

        Side effects:
            - May create a new thread in the store via create_thread()
            - May append a system message if backfilling a bare thread
            - Mutates session.threads in-place to reflect changes
            - Emits structured logs on thread creation and prompt backfill

        Dependencies:
            - agents.registry.get_prompt — loads prompt from scenario.yaml
        """
        # Default agent_id to "orchestrator" if empty
        agent_id = agent_id or "orchestrator"
        thread = session.threads.get(agent_id)

        if thread is None:
            # Thread doesn't exist — create it with the system prompt
            from agents import registry as _agent_registry
            _, display_name, prompt_text = _agent_registry.get_prompt(agent_id)

            # Create thread with system prompt as message 0 via the store
            thread = await store.create_thread(
                session_id, agent_id, display_name, prompt_text
            )
            # Update the in-memory session object so subsequent reads see it
            session.threads[agent_id] = thread

            logger.info(
                "session_state.thread_created",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "agent_name": display_name,
                    "prompt_chars": len(prompt_text),
                },
            )
            # New thread — first message by definition
            return thread, True

        # Thread exists — check if it has non-system messages
        non_system = [m for m in thread.messages if m.role != Role.SYSTEM]
        is_first_message = len(non_system) == 0

        # Load the expected prompt for the active scenario. Existing threads
        # may have been created under a different scenario, so we validate
        # message 0 against the current prompt before reusing the thread.
        from agents import registry as _agent_registry
        _, display_name, prompt_text = _agent_registry.get_prompt(agent_id)

        # If thread exists but has no system prompt (bare thread from
        # append_message auto-create before this fix), backfill one now
        if not thread.messages or thread.messages[0].role != Role.SYSTEM:
            # Insert system prompt as message 0 in-memory
            sys_msg = Message(role=Role.SYSTEM, content=prompt_text, agent_name=agent_id)
            thread.messages.insert(0, sys_msg)

            # Persist via the store
            await store.append_message(session_id, sys_msg, agent_id=agent_id)

            logger.info(
                "session_state.prompt_backfilled",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "prompt_chars": len(prompt_text),
                },
            )

        # If the thread already has a system prompt but it belongs to a
        # previous scenario, refresh it in place. Scenario switches clear the
        # agent config cache, but existing session threads persist across the
        # switch. Without this check, a hello-world session can keep the old
        # telecom orchestrator instructions and delegate to nonexistent agents.
        elif thread.messages[0].content != prompt_text:
            thread.agent_name = display_name
            thread.messages[0].content = prompt_text
            thread.messages[0].agent_name = agent_id

            # Persist the refreshed system message for both in-memory and
            # Cosmos stores. update_message rewrites the existing message doc
            # when the backend stores messages separately.
            await store.update_message(session_id, thread.messages[0], agent_id=agent_id)

            logger.info(
                "session_state.prompt_refreshed",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "agent_name": display_name,
                    "prompt_chars": len(prompt_text),
                },
            )

        return thread, is_first_message

    def build_turn_context(
        self,
        thread: AgentThread,
        agent_id: str,
        user_message: str,
        max_context_turns: int | None = None,
        agent_session_id: str = "",
    ) -> tuple[list[dict], ContextSnapshot]:
        """Build the LLM context window from the agent's thread.

        Extracts the system prompt from message 0 (if role=system), builds
        the token-budgeted context window, and produces a ContextSnapshot
        for auditability.

        Thread isolation is enforced by construction — this method receives
        only the target agent's thread. No cross-agent messages are possible.

        Args:
            thread: The agent's thread (must exist — call ensure_thread first).
            agent_id: Agent config key (for the snapshot).
            user_message: The user's query text (for the snapshot).
            max_context_turns: Max conversation turn pairs (None = unlimited).
            agent_session_id: Thread's SDK session ID (for the snapshot).

        Returns:
            (context_window, snapshot) — the message dicts for the LLM and
            the audit snapshot to store on the assistant message.

        Side effects:
            None — pure function (delegates to build_context_window which
            emits structured logs and OTel metrics).

        Dependencies:
            - build_context_window — token-budgeted sliding window
            - build_context_snapshot — JSON-serializable audit record
        """
        # Extract system prompt and conversation messages from the thread
        thread_msgs = thread.messages
        if thread_msgs and thread_msgs[0].role == Role.SYSTEM:
            sys_prompt = thread_msgs[0].content
            conv_msgs = thread_msgs[1:]  # Skip system message
        else:
            sys_prompt = None
            conv_msgs = thread_msgs

        # Build token-budgeted context window (isolation by construction —
        # only this agent's messages are present in conv_msgs)
        context_window, tokens_used = build_context_window(
            conv_msgs, system_prompt=sys_prompt, max_turns=max_context_turns
        )

        # Build audit snapshot for the ContextInspector.
        # Pass tokens_used from build_context_window to avoid re-tokenizing.
        snapshot_dict = build_context_snapshot(
            context_window,
            tokens_used=tokens_used,
            agent_session_id=agent_session_id or thread.agent_session_id,
            agent_id=agent_id,
            messages_total=len(conv_msgs),
            max_turns=max_context_turns,
            user_message=user_message,
        )
        snapshot = ContextSnapshot(**snapshot_dict)

        return context_window, snapshot
