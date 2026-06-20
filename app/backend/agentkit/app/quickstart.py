"""create_app — the quickstart one-liner over :class:`AgentApp`.

Module role:
    Collapses the common-case ``AgentApp(...)`` construction into a single
    keyword call so a new consumer stands up a streaming agent without
    memorising the facade's full surface or the fail-closed tool-allowlist
    footgun. ``AgentApp`` itself is unchanged — this is a thin additive wrapper
    that fills in the two ergonomic gaps:

      1. **Default settings** — when ``settings`` is omitted, build a sane
         instance via :meth:`BaseAgentSettings.from_env` so a local-dev
         quickstart needs no explicit settings object.
      2. **Tool-prefix normalisation** — ``tools_prefix`` accepts a single
         string (the overwhelmingly common case) or a tuple, and normalises it
         to the ``allowed_tool_prefixes`` tuple the resolver wants. This is the
         fix for the fail-closed footgun: the common case is now trivial.

Layer rule:
    ``agentkit.*`` only — no consumer package, no SDK at module load
    (``AgentApp`` keeps ``fastapi``/``uvicorn``/``agent_framework`` lazy).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentkit.app.agent_app import AgentApp
from agentkit.config import BaseAgentSettings

__all__ = ["create_app"]


def _normalise_tools_prefix(
    tools_prefix: str | tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    """Normalise ``tools_prefix`` to the ``allowed_tool_prefixes`` tuple.

    ``None`` → ``()`` (the fail-closed default — every tool import forbidden).
    A bare ``str`` → a one-element tuple. A tuple/list → a tuple of its items.
    """
    if tools_prefix is None:
        return ()
    if isinstance(tools_prefix, str):
        return (tools_prefix,)
    return tuple(tools_prefix)


def create_app(
    *,
    settings: BaseAgentSettings | None = None,
    config: str | Path,
    agent_client: Any,
    tools_prefix: str | tuple[str, ...] | list[str] | None = None,
    store: Any | None = None,
    default_agent_id: str | None = None,
    domain_events: tuple[str, ...] = (),
    tools: list[Any] | None = None,
    request_scope_builder: Callable[..., Any] | None = None,
    responses_client: Any | None = None,
    time_context_note: str = "",
) -> AgentApp:
    """Build a ready :class:`AgentApp` from the common-case arguments.

    Args:
        settings: A ``BaseAgentSettings`` (or subclass) instance. ``None`` (the
            default) builds one via :meth:`BaseAgentSettings.from_env` — handy
            for a local-dev quickstart. For an env-independent quickstart, pass
            an explicit instance (e.g. ``BaseAgentSettings(auth_enabled=False)``)
            so ambient ``AUTH_ENABLED`` cannot ValidationError the build.
        config: Path to ``agent_config.yaml`` or to the control directory that
            holds it (+ a ``prompts/`` sibling).
        agent_client: The injected ``AgentClient`` — a zero-arg ``() -> client``
            factory (preferred) or a client instance. The ONLY SDK seam. For a
            real Azure model use :func:`agentkit.sdk.azure_client.azure_openai_agent_client`.
        tools_prefix: The fail-closed import allowlist made trivial — a single
            package prefix string (``"tools."``) or a tuple of them. ``None``
            forbids every tool import (the fail-closed default).
        store: Optional injected ``SessionStore``. Defaults to a pure in-memory
            store (zero-infra quickstart).
        default_agent_id: Fallback agent id when the config omits a ``default``
            and ``chat`` is called without an ``agent_id``. ``None`` → ``""``.
        domain_events: Raw-string SSE event names to register atop the generic
            vocabulary.
        tools: Optional programmatic tool list (tools are normally declared in
            the YAML).
        request_scope_builder: Optional per-request scope builder (K9 seam).
        responses_client: Optional Responses-API client factory.
        time_context_note: Optional source-timezone note for the time provider.

    Returns:
        A ready :class:`AgentApp` whose ``.chat()`` / ``.router()`` / ``.serve()``
        work immediately.
    """
    resolved_settings = settings if settings is not None else BaseAgentSettings.from_env()
    allowed_tool_prefixes = _normalise_tools_prefix(tools_prefix)

    return AgentApp(
        resolved_settings,
        config,
        tools,
        agent_client=agent_client,
        store=store,
        request_scope_builder=request_scope_builder,
        allowed_tool_prefixes=allowed_tool_prefixes,
        default_agent_id=default_agent_id or "",
        domain_events=domain_events,
        responses_client=responses_client,
        time_context_note=time_context_note,
    )
