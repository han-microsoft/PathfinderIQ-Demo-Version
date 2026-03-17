"""Conversation service package — extracted concerns from router_chat.py.

Package role:
    Houses all conversation-layer logic that was previously inlined in
    route handlers. Each submodule owns one concern:

    - ``_context.py``    — token counting and sliding-window context assembly
    - ``_lifecycle.py``  — ConversationTurn: message assembly + finalization
    - ``_session_state.py`` — thread lifecycle + context building per agent
    - ``_metadata.py``   — title generation, activity summaries

Public API:
    Import directly from the package:
        ``from app.services.conversation import build_context_window, count_tokens``
        ``from app.services.conversation import ConversationTurn``
        ``from app.services.conversation import ConversationMetadata``

Key collaborators:
    - ``app.routers.chat`` — primary consumer
    - ``app.services.session_store.memory`` — uses ConversationMetadata
"""

from app.services.conversation._context import build_context_window, build_context_snapshot, count_tokens
from app.services.conversation._lifecycle import ConversationTurn
from app.services.conversation._metadata import ConversationMetadata
from app.services.conversation._session_state import SessionStateManager

__all__ = [
    "build_context_window",
    "build_context_snapshot",
    "count_tokens",
    "ConversationTurn",
    "ConversationMetadata",
    "SessionStateManager",
]
