"""Cosmos DB NoSQL session store — separate docs for session + messages.

Module role:
    Implements the ``SessionStore`` protocol using Azure Cosmos DB NoSQL
    with serverless capacity. Follows patterns from Microsoft's
    ``azure-search-openai-demo`` and ``chat-with-your-data-solution-accelerator``.

Design decisions:
    - All writes awaited inline (not fire-and-forget)
    - RBAC-only auth via ``DefaultAzureCredential`` — no keys
    - Separate documents per message (not one big Session document)
    - Denormalized counters on session doc for efficient ``list_all()``
    - ``patch_item`` for atomic counter increments
    - ``message.id``-based doc IDs — no sequential index, no race condition
    - ``created_at``-based ordering — no index field needed

Depends on:
    - ``azure-cosmos>=4.9.0``
    - ``azure-identity``
    - ``app.models`` (Session, SessionSummary, Message)
    - ``app.observability`` (get_tracer)

Called by:
    - ``main.py`` store selection (when ``COSMOS_SESSION_ENDPOINT`` is set)
    - ``deps.py`` via ``app.state.store``

Dependents:
    - ``router_sessions.py`` — CRUD endpoints
    - ``router_chat.py`` — streaming calls ``append_message``, ``update_message``
    - ``_store_with_retry`` in ``router_chat.py`` — wraps calls with retry
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from azure.cosmos.exceptions import CosmosResourceNotFoundError

from app.foundation.models import AgentThread, Message, Role, Session, SessionSummary
from app.observability import get_tracer
from app.foundation.resilience import registry
from app.services.session_store import SessionStoreUnavailable

# Logger — JSON formatter and correlation ID filter apply automatically
logger = logging.getLogger(__name__)

# OTel tracer — noop when OTEL_EXPORT_TARGET is empty
tracer = get_tracer(__name__)


class CosmosSessionStore:
    """Cosmos DB NoSQL session store — separate docs for session + messages.

    Partition key: ``/session_id``. Session metadata and messages co-located
    in the same partition for single-partition reads.

    Lifecycle:
        Created once at app startup in ``main.py``. Stored on ``app.state.store``.
        Closed on shutdown via ``close()``.

    Collaborators:
        - ``router_sessions.py`` — CRUD endpoints call protocol methods
        - ``router_chat.py`` — streaming calls ``append_message``, ``update_message``
        - ``_store_with_retry`` in ``router_chat.py`` — wraps calls with retry
        - ``app.resilience.registry`` — circuit breaker for Cosmos ("cosmos_sessions")
    """

    def __init__(self, endpoint: str, database: str, container: str) -> None:
        """Initialise Cosmos client and container reference.

        Args:
            endpoint: Cosmos DB account endpoint (https://<name>.documents.azure.com:443/)
            database: Database name (default: "sessions")
            container: Container name (default: "conversations")

        Side effects:
            Creates a ``DefaultAzureCredential`` and ``CosmosClient`` singleton.
        """
        self._credential = DefaultAzureCredential()
        self._client = CosmosClient(url=endpoint, credential=self._credential)
        self._container = (
            self._client.get_database_client(database)
            .get_container_client(container)
        )
        # Scenario filter for list_all() — set from settings in main.py
        self._scenario: str = ""
        # Template session IDs — populated during seed_saved_conversations().
        # Used by _ensure_user_seeded() to clone demos for new users.
        self._template_ids: list[str] = []
        # Set of user OIDs that have been seeded with cloned demo sessions.
        # In-memory cache — avoids redundant Cosmos queries on repeated list_all() calls.
        # On restart, empty set triggers a cheap count query (see _ensure_user_seeded).
        self._seeded_users: set[str] = set()
        # Lock for seeding — prevents duplicate demo session creation when
        # two concurrent requests arrive for the same new user.
        self._seed_lock = asyncio.Lock()
        # Circuit breaker — trips after 3 consecutive Cosmos failures.
        # Cooldown 30s — Cosmos outages are often transient (failover).
        # Created directly (not via registry.get_or_create) for per-instance
        # isolation in tests. Registered in main.py after store selection.
        from app.foundation.resilience import CircuitBreaker
        self._breaker = CircuitBreaker(
            "cosmos_sessions", failure_threshold=3, cooldown_secs=30
        )

    # ── Circuit breaker helper ───────────────────────────────────────

    def _check_breaker(self) -> None:
        """Raise SessionStoreUnavailable if the circuit breaker is open.

        Centralises the breaker-open check used by every protocol method.
        Methods that want a non-raising fallback (e.g. ``get`` returning
        None) should catch ``SessionStoreUnavailable`` at the call site.

        Raises:
            SessionStoreUnavailable: When the breaker is in OPEN state.
        """
        if self._breaker.is_open():
            raise SessionStoreUnavailable("Session store temporarily unavailable")

    def _record_ok(self) -> None:
        """Record a successful Cosmos operation on the circuit breaker."""
        self._breaker.record_success()

    def _record_fail(self, exc: Exception) -> SessionStoreUnavailable:
        """Record a Cosmos failure on the circuit breaker and wrap the exception.

        Args:
            exc: The original exception from the Cosmos SDK.

        Returns:
            A SessionStoreUnavailable wrapping the original exception.
        """
        self._breaker.record_failure()
        err = SessionStoreUnavailable("Session store temporarily unavailable")
        err.__cause__ = exc
        return err

    # ── Protocol methods ─────────────────────────────────────────────

    async def create(self, session: Session) -> Session:
        """Create session metadata doc with zeroed summary counters."""
        self._check_breaker()
        with tracer.start_as_current_span(
            "cosmos.session.create", attributes={"session_id": session.id, "user_id": session.user_id}
        ):
            try:
                t0 = time.monotonic()
                doc = {
                    "id": session.id,
                    "session_id": session.id,
                    "type": "session",
                    "user_id": session.user_id,
                    "scenario_name": session.scenario_name,
                    "title": session.title,
                    "message_count": 0,
                    "tool_call_count": 0,
                    "thinking_count": 0,
                    "user_prompt_count": 0,
                    "agent_response_count": 0,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                }
                await self._container.create_item(doc)
                self._record_ok()
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                logger.info(
                    "cosmos.session.created",
                    extra={
                        "session_id": session.id,
                        "user_id": session.user_id,
                        "scenario_name": session.scenario_name,
                        "duration_ms": elapsed,
                    },
                )
            except SessionStoreUnavailable:
                raise
            except Exception as e:
                raise self._record_fail(e)
        return session

    async def get(self, session_id: str) -> Session | None:
        """Read session doc + all message docs for a session.

        Returns None if session doesn't exist or the breaker is open.
        """
        try:
            self._check_breaker()
        except SessionStoreUnavailable:
            return None  # Degrade: session not found when Cosmos is down
        with tracer.start_as_current_span(
            "cosmos.session.get", attributes={"session_id": session_id}
        ):
            t0 = time.monotonic()
            try:
                session_doc = await self._container.read_item(
                    session_id, partition_key=session_id
                )
            except CosmosResourceNotFoundError:
                # Genuine 404 — do NOT trip the circuit breaker
                return None
            except Exception as e:
                raise self._record_fail(e)

            # Query message docs within the same partition — fast, ~5ms
            messages: list[Message] = []
            # Track agent_id per message for thread reconstruction
            msg_agent_ids: list[str] = []
            async for msg_doc in self._container.query_items(
                query=(
                    "SELECT * FROM c WHERE c.session_id=@sid"
                    " AND c.type='message' ORDER BY c.created_at"
                ),
                parameters=[{"name": "@sid", "value": session_id}],
                partition_key=session_id,
            ):
                messages.append(_doc_to_message(msg_doc))
                msg_agent_ids.append(msg_doc.get("agent_id", ""))

            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "cosmos.session.loaded",
                extra={
                    "session_id": session_id,
                    "message_count": len(messages),
                    "duration_ms": elapsed,
                },
            )
            self._record_ok()

            # Reconstruct threads from flat message docs.
            # Group messages by agent_id (empty → "orchestrator" default).
            threads: dict[str, AgentThread] = {}
            for msg, aid in zip(messages, msg_agent_ids):
                aid = aid or "orchestrator"
                if aid not in threads:
                    threads[aid] = AgentThread(
                        agent_id=aid,
                        agent_name=aid,
                        created_at=msg.created_at,
                    )
                threads[aid].messages.append(msg)

            return Session(
                id=session_doc["id"],
                title=session_doc.get("title", ""),
                schema_version=3,
                scenario_name=session_doc.get("scenario_name", ""),
                user_id=session_doc.get("user_id", ""),
                threads=threads,
                created_at=session_doc["created_at"],
                updated_at=session_doc["updated_at"],
            )

    async def list_all(self, user_id: str = "") -> list[SessionSummary]:
        """List sessions for the current scenario, filtered by user."""
        with tracer.start_as_current_span("cosmos.session.list_all"):
            self._check_breaker()

            # Lazy-seed demo conversations for authenticated users on first list call.
            # After seeding, user owns copies — no need to include __default__.
            if user_id:
                await self._ensure_user_seeded(user_id)

            t0 = time.monotonic()
            summaries: list[SessionSummary] = []
            query = "SELECT * FROM c WHERE c.type='session'"
            params: list[dict[str, Any]] = []
            if self._scenario:
                query += " AND c.scenario_name=@scenario"
                params.append({"name": "@scenario", "value": self._scenario})
            if user_id:
                # User is seeded — return only their own sessions (excludes __default__).
                query += " AND c.user_id=@uid"
                params.append({"name": "@uid", "value": user_id})
            query += " ORDER BY c.updated_at DESC"

            async for doc in self._container.query_items(
                query=query,
                parameters=params,
            ):
                summaries.append(
                    SessionSummary(
                        id=doc["id"],
                        title=doc.get("title", ""),
                        scenario_name=doc.get("scenario_name", ""),
                        user_id=doc.get("user_id", ""),
                        message_count=doc.get("message_count", 0),
                        tool_call_count=doc.get("tool_call_count", 0),
                        thinking_count=doc.get("thinking_count", 0),
                        user_prompt_count=doc.get("user_prompt_count", 0),
                        agent_response_count=doc.get("agent_response_count", 0),
                        created_at=doc["created_at"],
                        updated_at=doc["updated_at"],
                    )
                )

            elapsed = round((time.monotonic() - t0) * 1000, 1)
            logger.info(
                "cosmos.session.listed",
                extra={"count": len(summaries), "user_id": user_id or "(unfiltered)", "duration_ms": elapsed},
            )
            self._record_ok()
        return summaries

    async def update(self, session: Session) -> Session:
        """Update session metadata (title rename, etc.)."""
        self._check_breaker()
        with tracer.start_as_current_span(
            "cosmos.session.update", attributes={"session_id": session.id}
        ):
            try:
                t0 = time.monotonic()
                try:
                    existing = await self._container.read_item(
                        session.id, partition_key=session.id
                    )
                except CosmosResourceNotFoundError:
                    # Session doc doesn't exist — nothing to preserve.
                    # This shouldn't happen (update called on existing session)
                    # but handle defensively with empty baseline.
                    existing = {}
                except Exception as read_err:
                    raise self._record_fail(read_err)
                doc = {
                    **existing,
                    "id": session.id,
                    "session_id": session.id,
                    "type": "session",
                    "title": session.title,
                    "scenario_name": session.scenario_name,
                    "updated_at": session.updated_at.isoformat(),
                }
                await self._container.upsert_item(doc)
                self._record_ok()
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                logger.info(
                    "cosmos.session.updated",
                    extra={"session_id": session.id, "duration_ms": elapsed},
                )
            except SessionStoreUnavailable:
                raise
            except Exception as e:
                raise self._record_fail(e)
        return session

    async def delete(self, session_id: str) -> bool:
        """Delete session + all message docs within the partition."""
        self._check_breaker()
        with tracer.start_as_current_span(
            "cosmos.session.delete", attributes={"session_id": session_id}
        ):
            try:
                t0 = time.monotonic()
                ids: list[str] = []
                async for doc in self._container.query_items(
                    query="SELECT c.id FROM c WHERE c.session_id=@sid",
                    parameters=[{"name": "@sid", "value": session_id}],
                    partition_key=session_id,
                ):
                    ids.append(doc["id"])
                # Parallel delete in batches of 10 — same partition, safe for
                # concurrent operations. Reduces N sequential round-trips to
                # ceil(N/10) batched round-trips.
                _BATCH_SIZE = 10
                for i in range(0, len(ids), _BATCH_SIZE):
                    batch = ids[i:i + _BATCH_SIZE]
                    await asyncio.gather(*(
                        self._container.delete_item(doc_id, partition_key=session_id)
                        for doc_id in batch
                    ))
                self._record_ok()
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                logger.info(
                    "cosmos.session.deleted",
                    extra={
                        "session_id": session_id,
                        "docs_deleted": len(ids),
                        "duration_ms": elapsed,
                    },
                )
            except SessionStoreUnavailable:
                raise
            except Exception as e:
                raise self._record_fail(e)
        return len(ids) > 0

    async def append_message(self, session_id: str, message: Message, agent_id: str = "") -> None:
        """Create a new message doc and patch session counters atomically."""
        self._check_breaker()
        with tracer.start_as_current_span(
            "cosmos.message.append",
            attributes={"session_id": session_id, "role": message.role.value},
        ):
            try:
                t0 = time.monotonic()
                doc = {
                    "id": f"{session_id}-{message.id}",
                    "session_id": session_id,
                    "type": "message",
                    "message_id": message.id,
                    "role": message.role.value,
                    "content": message.content,
                    "status": message.status.value,
                    "tool_calls": [tc.model_dump(mode="json") for tc in message.tool_calls],
                    "agent_id": agent_id or message.agent_name or "",  # v3: thread attribution
                    "created_at": message.created_at.isoformat(),
                }
                await self._container.create_item(doc)

                # Atomically increment counters on the session doc
                tc_count = len(message.tool_calls)
                thinking = sum(1 for tc in message.tool_calls if tc.name == "thinking")
                role_field = (
                    "user_prompt_count"
                    if message.role.value == "user"
                    else "agent_response_count"
                )
                operations: list[dict[str, Any]] = [
                    {"op": "incr", "path": "/message_count", "value": 1},
                    {"op": "incr", "path": "/tool_call_count", "value": tc_count},
                    {"op": "incr", "path": "/thinking_count", "value": thinking},
                    {"op": "incr", "path": f"/{role_field}", "value": 1},
                    {"op": "set", "path": "/updated_at", "value": message.created_at.isoformat()},
                ]
                await self._container.patch_item(
                    item=session_id,
                    partition_key=session_id,
                    patch_operations=operations,
                )

                self._record_ok()
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                logger.info(
                    "cosmos.message.appended",
                    extra={
                        "session_id": session_id,
                        "message_id": message.id,
                        "role": message.role.value,
                        "tool_call_count": tc_count,
                        "duration_ms": elapsed,
                    },
                )
            except SessionStoreUnavailable:
                raise
            except Exception as e:
                raise self._record_fail(e)

    async def update_message(self, session_id: str, message: Message, agent_id: str = "") -> None:
        """Upsert a message doc (finalize streaming content)."""
        self._check_breaker()
        with tracer.start_as_current_span(
            "cosmos.message.update",
            attributes={"session_id": session_id, "message_id": message.id},
        ):
            try:
                t0 = time.monotonic()
                doc = {
                    "id": f"{session_id}-{message.id}",
                    "session_id": session_id,
                    "type": "message",
                    "message_id": message.id,
                    "role": message.role.value,
                    "content": message.content,
                    "status": message.status.value,
                    "tool_calls": [tc.model_dump(mode="json") for tc in message.tool_calls],
                    "agent_id": agent_id or message.agent_name or "",  # v3: thread attribution
                    "created_at": message.created_at.isoformat(),
                }
                await self._container.upsert_item(doc)
                self._record_ok()
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                logger.info(
                    "cosmos.message.updated",
                    extra={
                        "session_id": session_id,
                        "message_id": message.id,
                        "status": message.status.value,
                        "duration_ms": elapsed,
                    },
                )
            except SessionStoreUnavailable:
                raise
            except Exception as e:
                raise self._record_fail(e)

    async def get_thread(self, session_id: str, agent_id: str) -> AgentThread | None:
        """Retrieve a single agent's thread by loading the full session.

        Cosmos stores messages as flat docs — we reconstruct threads on read.
        This delegates to ``get()`` and returns the requested thread.

        Args:
            session_id: Session partition key.
            agent_id: Agent thread key to retrieve.

        Returns:
            AgentThread if found, None otherwise.
        """
        session = await self.get(session_id)
        if session is None:
            return None
        return session.threads.get(agent_id)

    async def create_thread(
        self, session_id: str, agent_id: str, agent_name: str, system_prompt: str = ""
    ) -> AgentThread:
        """Create a thread by appending a system prompt message.

        Cosmos doesn't store threads as separate docs — threads are
        reconstructed from message docs on read. Creating a thread means
        appending the system prompt as the first message with the given agent_id.

        Args:
            session_id: Session partition key.
            agent_id: Config key for the agent.
            agent_name: Display name for the agent.
            system_prompt: System prompt text (stored as first message).

        Returns:
            An AgentThread stub (actual thread is reconstructed on read).
        """
        thread = AgentThread(agent_id=agent_id, agent_name=agent_name)
        if system_prompt:
            sys_msg = Message(role=Role.SYSTEM, content=system_prompt, agent_name=agent_id)
            await self.append_message(session_id, sys_msg, agent_id=agent_id)
            thread.messages.append(sys_msg)
        return thread

    async def get_thread_messages(self, session_id: str, thread_id: str) -> list[Message]:
        """Return messages for a specific agent thread.

        Loads the full session and filters to the requested thread.

        Args:
            session_id: Session partition key.
            thread_id: Agent ID to filter by (e.g. "orchestrator").

        Returns:
            List of Message objects for the thread, or empty list.
        """
        session = await self.get(session_id)
        if session is None:
            return []
        thread = session.threads.get(thread_id)
        if thread is None:
            return []
        return list(thread.messages)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def is_healthy(self, timeout: float = 2.0) -> bool:
        """Check Cosmos container reachability — validates connectivity + auth.

        Wraps the container properties read in ``asyncio.wait_for()`` to prevent
        the SDK's default retry policy (9 retries, 30s max) from blocking startup.
        The timeout only applies to this health check — normal CRUD operations
        retain the full retry policy.

        Used for:
            - Startup: verify before committing to Cosmos (fallback on failure)
            - /health/ready: component-level health check
            - Cold-start warmup: first call warms the serverless instance

        Args:
            timeout: Maximum seconds to wait for container.read(). Default 2.0.
                     Callers can pass a higher value if desired.

        Returns:
            True if container responds within timeout, False otherwise.

        Side effects:
            Logs a warning if the timeout is exceeded (distinguishes "slow"
            from "firewalled" in operational logs).
        """
        import asyncio
        try:
            await asyncio.wait_for(self._container.read(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "cosmos.health_check.timeout",
                extra={"timeout_s": timeout},
            )
            return False
        except Exception:
            return False

    async def close(self) -> None:
        """Close the Cosmos client and credential.

        Called from main.py shutdown handler.
        """
        await self._client.close()
        await self._credential.close()

    # ── Per-user demo seeding ──────────────────────────────────────

    async def _ensure_user_seeded(self, user_id: str) -> None:
        """Clone ``__default__`` template sessions for a first-time user.

        Delegates to the shared ``clone_templates_for_user()`` algorithm.
        This method provides Cosmos-specific data access: count query for
        existence check, and create + append_message for persistence.

        Args:
            user_id: Entra object ID of the authenticated user.
        """
        from app.services.session_store._user_seeding import clone_templates_for_user, UserSeedingState

        # Fast path — already seeded this process lifetime
        if user_id in self._seeded_users:
            return

        async with self._seed_lock:
            # Double-check after acquiring lock
            if user_id in self._seeded_users:
                return
            if not self._template_ids:
                self._seeded_users.add(user_id)
                return

        # Check if user already has any own sessions (cold start after restart).
        # A single cross-partition COUNT query is ~3 RU.
        try:
            count = 0
            async for row in self._container.query_items(
                query=(
                    "SELECT VALUE COUNT(1) FROM c"
                    " WHERE c.type='session' AND c.user_id=@uid"
                ),
                parameters=[{"name": "@uid", "value": user_id}],
            ):
                count = row
            if count > 0:
                self._seeded_users.add(user_id)
                return
        except Exception as e:
            logger.warning("seed.user_check_failed: %s — skipping seed for %s", e, user_id)
            return

        # Delegate cloning to shared algorithm
        _temp_state = UserSeedingState()
        _temp_state._template_ids = list(self._template_ids)

        clones = await clone_templates_for_user(user_id, _temp_state, self.get)

        # Persist clones via Cosmos create + append_message
        for clone_session, cloned_threads in clones:
            try:
                await self.create(clone_session)
                for thread_id, thread in cloned_threads.items():
                    for msg in thread.messages:
                        await self.append_message(clone_session.id, msg, agent_id=thread_id)
            except Exception as e:
                logger.warning(
                    "seed.user_persist_failed: %s — clone=%s user=%s",
                    e, clone_session.id, user_id,
                )

        self._seeded_users.add(user_id)

    # ── Saved conversation seeding ───────────────────────────────────

    async def seed_saved_conversations(self, scenario_dir: Path | None) -> None:
        """Load saved conversation JSON files from disk into Cosmos.

        Delegates template discovery and parsing to the shared
        ``load_templates_from_disk()`` function. This method provides
        Cosmos-specific persistence: point-read existence check and
        create + append_message for new sessions.

        Idempotent — skips sessions whose ID already exists in Cosmos.

        Args:
            scenario_dir: Path to the active scenario directory. None = skip.
        """
        from app.services.session_store._user_seeding import (
            load_templates_from_disk,
            UserSeedingState,
        )
        # Build a temporary state to collect template IDs
        _temp_state = UserSeedingState()
        _temp_state._template_ids = self._template_ids  # Share the list reference

        sessions = load_templates_from_disk(scenario_dir, self._scenario, _temp_state)

        seeded = 0
        skipped = 0
        for session in sessions:
            try:
                # Check if already in Cosmos — point read, ~1 RU
                existing = await self.get(session.id)
                if existing is not None:
                    skipped += 1
                    continue

                # Create session doc (zeroed counters)
                await self.create(session)

                # Create message docs + increment counters via append_message
                for thread_id, thread in session.threads.items():
                    for msg in thread.messages:
                        await self.append_message(session.id, msg, agent_id=thread_id)

                seeded += 1
                logger.info(
                    "cosmos.session.seeded",
                    extra={
                        "session_id": session.id,
                        "title": session.title,
                    },
                )
            except Exception as e:
                logger.warning("Failed to seed %s: %s", session.id, e)

        if seeded or skipped:
            logger.info(
                "Saved conversation seeding complete: %d seeded, %d already present",
                seeded, skipped,
            )


# ── Helpers ──────────────────────────────────────────────────────────────


def _doc_to_message(doc: dict[str, Any]) -> Message:
    """Convert a Cosmos message document back to a Message model.

    Args:
        doc: Raw Cosmos document dict with role, content, status, tool_calls, etc.

    Returns:
        Validated Message instance with agent_name populated from agent_id.
    """
    return Message.model_validate({
        "id": doc.get("message_id", doc["id"]),
        "role": doc["role"],
        "content": doc.get("content", ""),
        "status": doc.get("status", "complete"),
        "tool_calls": doc.get("tool_calls", []),
        "agent_name": doc.get("agent_id", ""),  # v3: maps agent_id → Message.agent_name
        "created_at": doc.get("created_at"),
    })
