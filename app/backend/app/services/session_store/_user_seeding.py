"""Shared user-seeding — state tracking, template loading, and clone algorithm.

Module role:
    Provides ``UserSeedingState`` (state tracker) and two shared async
    functions that implement the seeding algorithms previously duplicated
    between InMemorySessionStore and CosmosSessionStore:

      - ``load_templates_from_disk()`` — reads saved_conversations/*.json,
        validates, sets user_id='__default__', registers template IDs.
        Returns a list of Session objects. The caller decides how to persist.

      - ``clone_templates_for_user()`` — clones each registered template
        for a specific user with new IDs. Uses a caller-provided async
        ``get_template`` callback (dict lookup or Cosmos read) and returns
        a list of (clone_session, cloned_threads) tuples. The caller
        decides how to persist.

    By extracting these algorithms, each store only implements ~5 lines
    of I/O-specific glue code instead of ~90 lines of duplicated logic.

Key collaborators:
    - app.services.session_store.memory  — composes this module
    - app.services.session_store.cosmos  — composes this module

Dependents:
    Called by: InMemorySessionStore, CosmosSessionStore
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class UserSeedingState:
    """Tracks which templates exist and which users have been seeded.

    Encapsulates the state that was previously duplicated across both
    session store implementations: _template_ids and _seeded_users.

    Thread safety:
        This class holds primitive state (list + set). The caller is
        responsible for any locking needed around the seeding operation
        itself. The state mutations here (append, add, discard) are
        individually atomic in CPython but the overall seed operation
        should be protected by the store's existing async lock.

    Lifecycle:
        Created in the store's __init__. Populated during load_saved()
        or seed_saved_conversations(). Queried on every list_all() call.
    """

    def __init__(self) -> None:
        """Initialise empty template and seeded-user tracking."""
        # Template session IDs — populated during saved conversation loading.
        # Used by the store's _ensure_user_seeded() to know what to clone.
        self._template_ids: list[str] = []
        # Set of user OIDs that have been seeded with cloned demo sessions.
        # In-memory only — reset on restart. The store's _ensure_user_seeded
        # performs a cheap check (dict scan or COUNT query) on cold start.
        self._seeded_users: set[str] = set()

    def register_template(self, session_id: str) -> None:
        """Register a session as a template for cloning. Deduplicates.

        Args:
            session_id: ID of the __default__ session loaded from disk.

        Side effects:
            Appends to _template_ids if not already present.
        """
        if session_id not in self._template_ids:
            self._template_ids.append(session_id)

    @property
    def template_ids(self) -> list[str]:
        """Return a copy of the template ID list."""
        return list(self._template_ids)

    def should_seed(self, user_id: str) -> bool:
        """Determine whether a user needs demo session seeding.

        Fast-path checks:
          1. Already seeded this process lifetime → False
          2. No templates registered → mark seeded, return False

        Args:
            user_id: Entra object ID of the authenticated user.

        Returns:
            True if the user should be seeded, False if already done or
            no templates exist.
        """
        # Fast path — already seeded this process lifetime
        if user_id in self._seeded_users:
            return False
        # No templates loaded — nothing to seed
        if not self._template_ids:
            self._seeded_users.add(user_id)
            return False
        return True

    def mark_seeded(self, user_id: str) -> None:
        """Mark a user as seeded — prevents re-seeding on subsequent calls.

        Args:
            user_id: Entra object ID that was just seeded (or skipped).
        """
        self._seeded_users.add(user_id)

    def is_seeded(self, user_id: str) -> bool:
        """Check if a user has been marked as seeded.

        Args:
            user_id: Entra object ID to check.

        Returns:
            True if the user has been marked as seeded.
        """
        return user_id in self._seeded_users

    def reset(self) -> None:
        """Clear all seeding state. Used during scenario switches
        or test cleanup to force re-seeding on next request."""
        self._template_ids.clear()
        self._seeded_users.clear()


# ── Shared algorithms ────────────────────────────────────────────────────────
# These functions implement the seeding logic that was previously duplicated
# between memory.py (~90 lines) and cosmos.py (~120 lines).


import json
import uuid
from pathlib import Path
from typing import Any, Callable, Awaitable

from app.foundation.models import AgentThread, Message, Session


def load_templates_from_disk(
    scenario_dir: Path | None,
    scenario_name: str,
    seeding_state: UserSeedingState,
) -> list[Session]:
    """Load saved conversation JSON files from disk and register as templates.

    Reads ``{scenario_dir}/saved_conversations/*.json``, validates each as a
    Session, sets ``user_id='__default__'``, aligns ``scenario_name``, and
    registers the ID as a template in ``seeding_state``.

    The caller is responsible for persisting the returned sessions (dict
    insertion for memory, Cosmos create for cloud).

    Args:
        scenario_dir: Path to the active scenario directory. None → empty list.
        scenario_name: Active scenario name (for alignment).
        seeding_state: The UserSeedingState to register template IDs into.

    Returns:
        List of validated Session objects ready to persist. Empty on no dir/files.
    """
    if scenario_dir is None:
        return []
    save_dir = scenario_dir / "saved_conversations"
    if not save_dir.is_dir():
        return []

    sessions: list[Session] = []
    for filepath in sorted(save_dir.glob("*.json")):
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            session = Session.model_validate(data)
            # Saved conversations are shared templates visible to all users
            session.user_id = "__default__"
            # Align scenario_name so sessions match list_all() scenario filter
            if scenario_name:
                session.scenario_name = scenario_name
            # Register template ID for per-user cloning
            seeding_state.register_template(session.id)
            sessions.append(session)
        except Exception as e:
            logger.warning("Failed to load %s: %s", filepath.name, e)

    if sessions:
        logger.info(
            "Loaded %d saved conversation template(s) from %s",
            len(sessions), save_dir,
        )
    return sessions


async def clone_templates_for_user(
    user_id: str,
    seeding_state: UserSeedingState,
    get_template: Callable[[str], Awaitable[Session | None]],
) -> list[tuple[Session, dict[str, AgentThread]]]:
    """Clone registered template sessions for a specific user.

    Generates new IDs for the session and all its messages. Returns the
    clones as a list of ``(session, threads_dict)`` tuples — the caller
    persists them using their backend-specific write operations.

    Args:
        user_id: Entra object ID of the user to clone for.
        seeding_state: State tracker with template IDs to clone.
        get_template: Async callback that retrieves a template Session by ID.
            For InMemory: ``async lambda tid: store._sessions.get(tid)``
            For Cosmos: ``store.get``

    Returns:
        List of (cloned_session, cloned_threads) tuples. The threads dict
        maps thread_id → AgentThread with cloned messages.
        Empty list if no templates or all fetches fail.
    """
    clones: list[tuple[Session, dict[str, AgentThread]]] = []

    for template_id in seeding_state.template_ids:
        try:
            template = await get_template(template_id)
            if template is None:
                continue

            clone_id = uuid.uuid4().hex
            cloned_threads: dict[str, AgentThread] = {}
            total_msg_count = 0

            for tid, thread in template.threads.items():
                cloned_msgs = [
                    Message(
                        id=uuid.uuid4().hex,
                        role=msg.role,
                        content=msg.content,
                        status=msg.status,
                        tool_calls=msg.tool_calls,
                        agent_name=msg.agent_name,
                        created_at=msg.created_at,
                    )
                    for msg in thread.messages
                ]
                cloned_threads[tid] = AgentThread(
                    agent_id=thread.agent_id,
                    agent_name=thread.agent_name,
                    messages=cloned_msgs,
                    created_at=thread.created_at,
                )
                total_msg_count += len(cloned_msgs)

            clone = Session(
                id=clone_id,
                title=template.title,
                scenario_name=template.scenario_name,
                user_id=user_id,
                threads=cloned_threads,
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            clones.append((clone, cloned_threads))

            logger.info(
                "seed.user_session_cloned",
                extra={
                    "user_id": user_id,
                    "template_id": template_id,
                    "clone_id": clone_id,
                    "message_count": total_msg_count,
                },
            )
        except Exception as e:
            logger.warning(
                "seed.user_clone_failed: %s — template=%s user=%s",
                e, template_id, user_id,
            )

    if clones:
        logger.info(
            "seed.user_complete",
            extra={"user_id": user_id, "sessions_cloned": len(clones)},
        )
    return clones
