"""Dependency injection via FastAPI's ``app.state``.

Module role:
    Provides FastAPI ``Depends()`` callables that extract singleton services
    from the application state. These services are created once during the
    ``lifespan`` context manager in ``main.py`` and reused across all requests.

Key collaborators:
    - ``app.main.lifespan``            – creates and attaches services to ``app.state``
    - ``app.services.llm.LLMService``  – protocol for LLM providers
    - ``app.services.session_store.SessionStore`` – protocol for session persistence

Dependents:
    Called by: ``routers/chat.py``, ``routers/sessions.py`` via FastAPI ``Depends()``

Design rationale:
    Decouples route handlers from service instantiation. Route handlers declare
    dependencies via type hints, and FastAPI's DI system resolves them at
    request time using these factory functions.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.auth import User, get_current_user  # noqa: F401 — re-exported for router imports
from app.services.llm import LLMService
from app.services.session_store import SessionStore


def get_store(request: Request) -> SessionStore:
    """Retrieve the session store singleton from ``app.state``.

    Returns:
        SessionStore: Either CosmosSessionStore or InMemorySessionStore,
        depending on whether COSMOS_SESSION_ENDPOINT is configured.

    Dependents:
        Called by: routers/sessions.py, routers/chat.py via Depends(get_store)
    """
    return request.app.state.store


def get_llm(request: Request) -> LLMService:
    """Retrieve the LLM service singleton from ``app.state``.

    Returns:
        LLMService: One of OpenAILLMService, AgentFrameworkService,
        MockLLMService, or EchoLLMService — selected by LLM_PROVIDER env var.

    Dependents:
        Called by: routers/chat.py via Depends(get_llm)
    """
    return request.app.state.llm


def get_llmops(request: Request):
    """Retrieve the LLMOps trace manager from ``app.state``.

    Returns ``None`` when LLMOPS_BACKEND is empty (tracing disabled).
    The caller must check for None before calling ``.trace()``.

    Returns:
        LLMOpsTraceManager | None

    Dependents:
        Called by: routers/chat.py via Depends(get_llmops)
    """
    return getattr(request.app.state, "llmops", None)


def get_input_guardrails(request: Request) -> list:
    """Retrieve input guardrails from ``app.state``.

    Returns an empty list when no guardrails are configured — the
    runner skips execution on empty lists.

    Returns:
        list[InputGuardrail]

    Dependents:
        Called by: routers/chat.py via Depends(get_input_guardrails)
    """
    return getattr(request.app.state, "input_guardrails", [])


def get_output_guardrails(request: Request) -> list:
    """Retrieve output guardrails from ``app.state``.

    Returns:
        list[OutputGuardrail]

    Dependents:
        Called by: routers/chat.py via Depends(get_output_guardrails)
    """
    return getattr(request.app.state, "output_guardrails", [])
