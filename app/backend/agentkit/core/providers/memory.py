"""Cosmos DB-backed user memory context provider (K6).

Module role:
    Stores and retrieves per-user "memories" (key facts, investigation
    summaries) across sessions using a Cosmos container. Scoped by user_oid. The
    container client is injected via constructor (duck-typed: any object exposing
    ``query_items`` / ``upsert_item``). If ``None`` is passed, ``before_run``
    asks an injected resolver for the shared container.

    Fail-open: all errors caught and logged. Memory failure never blocks chat.

Layering:
    stdlib only. No GridIQ package. Was ``agent/providers/memory.py``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class CosmosUserMemoryProvider:
    """Cosmos DB-backed cross-session user memory.

    Each instance is scoped to one user_oid. Created per-request by the provider
    factory.

    Attributes:
        source_id: Provider identifier for attribution.
        user_oid: User's object ID (partition key scope).
        session_id: Current session ID (tagged on new memories).
        max_memories: Maximum memories to retrieve per before_run() call.
    """

    def __init__(
        self,
        user_oid: str,
        session_id: str = "",
        max_memories: int = 5,
        container_client: Any = None,
        container_resolver: Any = None,
    ) -> None:
        """Initialize the user memory provider.

        Args:
            user_oid: User's object ID. Scopes all queries.
            session_id: Current session ID (tagged on new memories).
            max_memories: Max memories to retrieve per before_run() call.
            container_client: Cosmos container proxy. None = lazy resolve.
            container_resolver: Async callable that resolves the container when
                one is not injected directly.
        """
        self.source_id = "user_memory"
        self.user_oid = user_oid
        self.session_id = session_id
        self.max_memories = max_memories
        self._container = container_client
        self._container_resolver = container_resolver

    async def _resolve_container(self) -> Any:
        """Resolve the Cosmos container — injected or lazy fallback.

        Returns:
            ContainerProxy or None.
        """
        if self._container is not None:
            return self._container
        try:
            if self._container_resolver is not None:
                self._container = await self._container_resolver()
        except Exception as e:
            logger.debug("memory.container.resolve_failed: %s", e)
        return self._container

    async def before_run(
        self, *, agent: Any, session: Any, context: Any, state: dict
    ) -> None:
        """Retrieve relevant user memories and inject as context instruction."""
        container = await self._resolve_container()
        if container is None:
            return

        try:
            query = (
                "SELECT TOP @max c.content, c.created_at "
                "FROM c WHERE c.user_oid = @user_oid "
                "ORDER BY c.created_at DESC"
            )
            params = [
                {"name": "@user_oid", "value": self.user_oid},
                {"name": "@max", "value": self.max_memories},
            ]

            memories: list[str] = []
            async for item in container.query_items(
                query=query,
                parameters=params,
                partition_key=self.user_oid,
            ):
                content = item.get("content", "")
                if content:
                    memories.append(content)

            if not memories:
                logger.debug(
                    "memory.before_run: no memories for user %s...",
                    self.user_oid[:8],
                )
                return

            memory_text = "\n".join(f"- {m}" for m in memories)
            instruction = (
                "## User Context\n"
                "The following facts are from this user's previous conversations. "
                "Use them as background context when relevant:\n\n"
                f"{memory_text}"
            )
            context.extend_instructions(self.source_id, instruction)

            logger.info(
                "memory.before_run.injected",
                extra={"user": self.user_oid[:8], "count": len(memories)},
            )

        except Exception as e:
            logger.warning("memory.before_run.failed: %s", str(e)[:200])

    async def after_run(
        self, *, agent: Any, session: Any, context: Any, state: dict
    ) -> None:
        """Extract key facts from the response and store as memories."""
        container = await self._resolve_container()
        if container is None:
            return

        response = getattr(context, "response", None)
        if not response:
            return

        response_messages = getattr(response, "messages", None)
        if not response_messages:
            return

        # Find the last assistant message text
        response_text = ""
        for msg in reversed(response_messages):
            role = getattr(msg, "role", "")
            role_str = str(role).lower()
            if "assistant" in role_str:
                response_text = getattr(msg, "text", "") or ""
                break

        if not response_text or len(response_text) < 50:
            return

        try:
            # Simple sentence extraction — take first 3 substantive sentences.
            raw_sentences = response_text.replace("\n", ". ").split(".")
            sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 30]
            facts = sentences[:3]

            if not facts:
                return

            now = datetime.now(timezone.utc).isoformat()
            for fact in facts:
                doc = {
                    "id": uuid.uuid4().hex,
                    "user_oid": self.user_oid,
                    "content": fact[:500],
                    "source_session_id": self.session_id,
                    "created_at": now,
                    "ttl": 2592000,  # 30 days
                }
                await container.upsert_item(doc)

            logger.info(
                "memory.after_run.stored",
                extra={
                    "user": self.user_oid[:8],
                    "facts": len(facts),
                    "session": self.session_id[:8] if self.session_id else "",
                },
            )

        except Exception as e:
            logger.warning("memory.after_run.failed: %s", str(e)[:200])
