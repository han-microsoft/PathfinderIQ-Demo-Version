"""In-memory session store for development and fallback.

Module role:
    Provides ``InMemorySessionStore`` — a thread-safe in-process dict that
    holds sessions in RAM. Used when no Cosmos DB endpoint is configured
    (local dev) or when Cosmos is unreachable at startup (degraded fallback).

    On startup, ``load_saved()`` reads ``saved_conversations/*.json`` from
    the active scenario directory to populate the store with prepared demo
    conversations. This ensures demo scenarios are always available in the
    sidebar regardless of session store health.

Key collaborators:
    - ``app.models.Session``, ``Message``, ``SessionSummary`` — stored objects
    - ``main.py`` — instantiates the store and calls ``load_saved()``
    - ``deps.py`` — injects the store into route handlers via ``app.state.store``

Dependents:
    Called by: ``routers/sessions.py`` (CRUD), ``routers/chat.py`` (message append/update)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.foundation.models import AgentThread, Message, Role, Session, SessionSummary
from app.services.conversation._metadata import ConversationMetadata

# Logger — JSON formatter and correlation ID filter apply automatically
logger = logging.getLogger(__name__)


class InMemorySessionStore:
    """Thread-safe in-memory session store for development and fallback.

    Not suitable for production — data is lost on restart and not shared
    across workers. Use ``CosmosSessionStore`` for durable persistence.

    Lifecycle:
        Created in ``main.py`` lifespan. Stored on ``app.state.store``.
        ``load_saved()`` called immediately after creation to seed saved
        demo conversations from disk.

    Collaborators:
        - ``routers/sessions.py`` — CRUD endpoints call protocol methods
        - ``routers/chat.py`` — streaming calls ``append_message``, ``update_message``
    """

    def __init__(self) -> None:
        """Initialise empty session dict and async lock."""
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()
        # Template session IDs — populated during load_saved().
        # Used by _ensure_user_seeded() to clone demos for new users.
        self._template_ids: list[str] = []
        # Set of user OIDs that have been seeded with cloned demo sessions.
        # In-memory only — reset on restart (load_saved re-populates templates).
        self._seeded_users: set[str] = set()

    async def is_healthy(self, timeout: float = 1.0) -> bool:
        """In-memory store is always healthy. Matches CosmosSessionStore API."""
        return True

    async def close(self) -> None:
        """No-op — no external resources to release. Matches CosmosSessionStore API."""
        pass

    async def create(self, session: Session) -> Session:
        """Store a session (including its messages list) in the dict.

        Args:
            session: Full Session object. Messages are stored inline.

        Returns:
            The same Session object.
        """
        async with self._lock:
            self._sessions[session.id] = session
        return session

    async def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID. Returns None if not found.

        Args:
            session_id: Session identifier.

        Returns:
            Session with messages, or None.
        """
        async with self._lock:
            return self._sessions.get(session_id)

    async def list_all(self, user_id: str = "") -> list[SessionSummary]:
        """List all sessions as summaries with computed counts.

        When user_id is non-empty (auth enabled):
          - Ensures the user has been seeded with cloned demo conversations
            (lazy init on first call — see ``_ensure_user_seeded()``).
          - Returns only sessions owned by that user (no ``__default__``).
        When user_id is empty (auth disabled):
          - Returns all sessions including ``__default__`` templates.

        Returns:
            List of SessionSummary sorted by updated_at descending.
            Counts are computed from the in-memory messages array.
        """
        # Lazy-seed demo conversations for authenticated users on first list call.
        if user_id:
            await self._ensure_user_seeded(user_id)

        # Snapshot session references under the lock, then release before
        # computing summaries. Summary computation is read-only and
        # O(total_messages) per session — holding the lock would block
        # concurrent append_message/update_message from chat streams.
        async with self._lock:
            snapshot = [
                s for s in self._sessions.values()
                if not user_id or s.user_id == user_id
            ]

        # Compute summaries outside the lock
        summaries = []
        for s in snapshot:
            summary_counts = ConversationMetadata.compute_summary_from_threads(s.threads)

            summaries.append(SessionSummary(
                id=s.id,
                title=s.title,
                scenario_name=s.scenario_name,
                user_id=s.user_id,
                message_count=summary_counts["message_count"],
                tool_call_count=summary_counts["tool_call_count"],
                thinking_count=summary_counts["thinking_count"],
                user_prompt_count=summary_counts["user_prompt_count"],
                agent_response_count=summary_counts["agent_response_count"],
                created_at=s.created_at,
                updated_at=s.updated_at,
            ))
        return sorted(summaries, key=lambda s: s.updated_at, reverse=True)

    async def update(self, session: Session) -> Session:
        """Replace session data and update the timestamp.

        Args:
            session: Session with updated fields.

        Returns:
            The updated Session.
        """
        async with self._lock:
            session.updated_at = datetime.now(timezone.utc)
            self._sessions[session.id] = session
        return session

    async def delete(self, session_id: str) -> bool:
        """Remove a session from the store.

        Args:
            session_id: Session identifier.

        Returns:
            True if a session was found and removed, False otherwise.
        """
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    async def append_message(self, session_id: str, message: Message, agent_id: str = "") -> None:
        """Append a message to an agent's thread in the session.

        The thread must already exist (created by SessionStateManager.ensure_thread).

        Args:
            session_id: Target session identifier.
            message: Message to append.
            agent_id: Agent thread to append to (empty = "orchestrator").

        Raises:
            KeyError: If session_id or thread does not exist.
        """
        agent_id = agent_id or "orchestrator"
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            if agent_id not in session.threads:
                raise KeyError(
                    f"Thread {agent_id!r} not found in session {session_id}. "
                    f"Call SessionStateManager.ensure_thread() before appending."
                )
            session.threads[agent_id].messages.append(message)
            session.updated_at = datetime.now(timezone.utc)

    async def update_message(self, session_id: str, message: Message, agent_id: str = "") -> None:
        """Replace a message in an agent's thread by ID match.

        Args:
            session_id: Target session identifier.
            message: Message with updated content (matched by message.id).
            agent_id: Agent thread to search (empty = search all threads).

        Raises:
            KeyError: If session_id does not exist.
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            threads_to_search = (
                [session.threads[agent_id]] if agent_id and agent_id in session.threads
                else session.threads.values()
            )
            for thread in threads_to_search:
                for i, m in enumerate(thread.messages):
                    if m.id == message.id:
                        thread.messages[i] = message
                        session.updated_at = datetime.now(timezone.utc)
                        return

    async def get_thread(self, session_id: str, agent_id: str) -> AgentThread | None:
        """Retrieve a single agent's thread from a session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return session.threads.get(agent_id)

    async def create_thread(
        self, session_id: str, agent_id: str, agent_name: str, system_prompt: str = ""
    ) -> AgentThread:
        """Create a new agent thread with optional system prompt as message 0."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")
            thread = AgentThread(agent_id=agent_id, agent_name=agent_name)
            if system_prompt:
                thread.messages.append(
                    Message(role=Role.SYSTEM, content=system_prompt, agent_name=agent_id)
                )
            session.threads[agent_id] = thread
            session.updated_at = datetime.now(timezone.utc)
            return thread

    async def get_thread_messages(self, session_id: str, thread_id: str) -> list:
        """Return messages belonging to a specific thread.

        Args:
            session_id: Target session identifier.
            thread_id: Thread discriminator (e.g. "orchestrator").

        Returns:
            List of Message objects matching the thread, sorted by created_at.
        """
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            # v3: get messages from the agent's thread
            thread = session.threads.get(thread_id)
            if thread is None:
                return []
            return list(thread.messages)

    # ── Per-user demo seeding ────────────────────────────────────────

    async def _ensure_user_seeded(self, user_id: str) -> None:
        """Clone ``__default__`` template sessions for a first-time user.

        Delegates to the shared ``clone_templates_for_user()`` algorithm.
        This method only provides the data-access glue: dict lookup for
        template retrieval and dict insertion for clone persistence.

        Args:
            user_id: Entra object ID of the authenticated user.
        """
        from app.services.session_store._user_seeding import clone_templates_for_user

        # Fast path — already seeded this process lifetime
        if user_id in self._seeded_users:
            return
        if not self._template_ids:
            self._seeded_users.add(user_id)
            return

        # Check if user already has any own sessions
        async with self._lock:
            has_own = any(
                s.user_id == user_id for s in self._sessions.values()
            )
        if has_own:
            self._seeded_users.add(user_id)
            return

        # Delegate cloning to shared algorithm
        async def _get_template(tid: str) -> Session | None:
            async with self._lock:
                return self._sessions.get(tid)

        # Use UserSeedingState from our instance attributes for template_ids
        from app.services.session_store._user_seeding import UserSeedingState
        _temp_state = UserSeedingState()
        _temp_state._template_ids = list(self._template_ids)

        clones = await clone_templates_for_user(user_id, _temp_state, _get_template)

        # Persist clones into the in-memory dict
        for clone_session, _threads in clones:
            async with self._lock:
                self._sessions[clone_session.id] = clone_session

        self._seeded_users.add(user_id)

    # ── Saved conversation loading ───────────────────────────────────

    async def load_saved(self, scenario_dir: Path | None) -> None:
        """Load saved conversation JSON files into the in-memory store.

        Delegates template discovery and parsing to the shared
        ``load_templates_from_disk()`` function. This method only
        provides the persistence glue: dict insertion.

        Args:
            scenario_dir: Path to the active scenario directory. None = skip.
        """
        from app.services.session_store._user_seeding import (
            load_templates_from_disk,
            UserSeedingState,
        )
        # Build a temporary UserSeedingState to collect template IDs
        _temp_state = UserSeedingState()
        _temp_state._template_ids = self._template_ids  # Share the list reference

        scenario_name = getattr(self, '_scenario', '')
        sessions = load_templates_from_disk(scenario_dir, scenario_name, _temp_state)

        loaded = 0
        for session in sessions:
            if session.id in self._sessions:
                continue
            async with self._lock:
                self._sessions[session.id] = session
            loaded += 1

        if loaded:
            logger.info("Loaded %d saved conversation(s) into memory store", loaded)
