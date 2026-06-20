"""AgentApp — the few-lines composition-root facade (K-capstone, increment 9).

Module role:
    Internalises the wiring a consumer's composition root would otherwise
    hand-assemble (GridIQ's ``app/_startup.py`` + ``app/main.py`` +
    ``agent/_compose.py``): settings registration, the agent registry + injected
    client factory, the fail-closed tool-resolver allowlist, the control
    directory / default-agent fallback / time note, the streaming vocabulary,
    and the session store. The result is a single object exposing the three
    surfaces a consumer needs — ``chat`` (the core run path), ``router`` (a
    mountable FastAPI ``APIRouter``), and ``serve`` (a uvicorn quickstart).

Owns vs. injects (the §9 open decision, resolved):
    OWNS   — settings registration, the ``AgentRegistry`` + per-agent client
             cache, control-dir / fallback / allowlist / time-note config, the
             generic SSE vocabulary, and the in-memory session-store DEFAULT.
    INJECTS— the ``AgentClient`` (factory, no SDK import in this module), the
             session ``store`` (in-memory default → zero-infra quickstart; a
             durable store is the consumer's two-phase concern), and the
             ``request_scope_builder`` (K9 stays the consumer's — the facade
             offers an injection point, not a generic builder).
    CONFIG — foundation prompts are config-driven (the top-level
             ``foundation_prompts:`` key of the agent YAML), not a constructor
             argument; the builder reads them from the loaded config.

Layer rule:
    ``agentkit.*`` imports only. No GridIQ package. ``fastapi`` / ``uvicorn``
    are imported lazily inside ``router`` / ``serve`` (the ``[fastapi]`` extra);
    the concrete SDK arrives via the injected ``agent_client`` factory so this
    module never imports ``agent_framework`` at load.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from agentkit.config import (
    BaseAgentSettings,
    configure_settings,
)
from agentkit.contracts.models import (
    Message,
    MessageStatus,
    Role,
    SessionBase,
    StreamEvent,
    StreamEventType,
    ToolCall,
)
from agentkit.core import (
    AgentRegistry,
    get_prompt,
    set_default_agent_fallback,
    set_default_allowed_prefixes,
    set_default_control_dir,
)
from agentkit.core.config_loader import default_agent_id as _resolve_default_agent_id
from agentkit.core.providers.time import set_time_context_note
from agentkit.hosting import (
    ToolCallBuffer,
    map_update_to_events,
    register_domain_events,
)
from agentkit.persistence import InMemorySessionStore

logger = logging.getLogger(__name__)


def _as_factory(agent_client: Any) -> Callable[[], Any]:
    """Normalise ``agent_client`` to a zero-arg client factory.

    The registry caches one client per agent_id to prevent SDK identity bleed
    (whichever agent builds first stamps its identity on a shared client), so it
    needs a *factory*. A bare client instance is wrapped in a constant factory —
    safe for the single-agent quickstart; multi-agent consumers should pass a
    factory so each agent gets its own client.
    """
    if callable(agent_client) and not hasattr(agent_client, "as_agent"):
        # A plain callable with no ``as_agent`` is already a factory.
        return agent_client
    return lambda: agent_client


class AgentApp:
    """Few-lines facade over the agentkit agent runtime.

    Args:
        settings: A ``BaseAgentSettings`` (or consumer subclass) instance. The
            facade registers it process-wide via ``configure_settings`` so every
            agentkit internal reads the same frozen config. Passing an explicit
            instance is what keeps a quickstart independent of any consumer's
            environment (no bare ``BaseAgentSettings()`` ValidationError).
        config: Path to the agent YAML (``agent_config.yaml``) or to the control
            directory that contains it (+ a ``prompts/`` sibling).
        tools: Optional list of tool callables/specs. Reserved for programmatic
            registration; tools are normally declared in the agent YAML and
            resolved by the builder. Kept on the instance for introspection.
        agent_client: The injected ``AgentClient`` — a zero-arg factory
            ``() -> client`` (preferred) or a client instance (wrapped). This is
            the ONLY SDK seam; the facade never imports a concrete SDK.
        store: Optional injected ``SessionStore``. Defaults to a pure
            in-memory store so the quickstart needs zero infrastructure. A
            durable backend (and its two-phase warmup) stays the consumer's
            concern.
        request_scope_builder: Optional callable building a per-request scope
            (K9). The facade exposes this injection point; it does not ship a
            generic builder. When provided, ``router`` applies it per request.
        allowed_tool_prefixes: Fail-closed importable-module allowlist for the
            tool resolver. Empty (the agentkit default) forbids every import —
            a consumer MUST pass its own (e.g. ``("tools.",)``).
        default_agent_id: Fallback agent id used when the config omits a
            ``default`` and ``chat`` is called without an ``agent_id``.
        domain_events: Raw-string SSE event names the consumer adds on top of
            the generic vocabulary (registered via ``register_domain_events``).
        responses_client: Optional Responses-API client factory for agents that
            declare ``client_type: responses``.
        time_context_note: Optional source-timezone note appended to the
            system-time provider instruction.
    """

    def __init__(
        self,
        settings: BaseAgentSettings,
        config: str | Path,
        tools: list[Any] | None = None,
        *,
        agent_client: Any,
        store: Any | None = None,
        request_scope_builder: Callable[..., Any] | None = None,
        allowed_tool_prefixes: tuple[str, ...] = (),
        default_agent_id: str = "",
        domain_events: tuple[str, ...] = (),
        responses_client: Any | None = None,
        time_context_note: str = "",
    ) -> None:
        # 1. Register the settings instance process-wide. Every agentkit
        #    internal (resilience fallback queue, builder model resolution,
        #    time provider) reads it via get_settings() — one frozen snapshot.
        configure_settings(settings)
        self.settings = settings

        # 2. Resolve the control directory from ``config`` (accept either the
        #    YAML file path or the directory holding it) and register it +
        #    the default-agent fallback for the zero-arg config loaders.
        config_path = Path(config).resolve()
        control_dir = config_path.parent if config_path.is_file() else config_path
        set_default_control_dir(control_dir)
        self._control_dir = control_dir
        if default_agent_id:
            set_default_agent_fallback(default_agent_id)
        self._default_agent_id = default_agent_id

        # 3. Fail-closed tool-import allowlist (B-RESOLVER-SILENT). The consumer
        #    owns this — agentkit ships no importable prefix by default.
        set_default_allowed_prefixes(tuple(allowed_tool_prefixes))

        # 4. Optional domain time note (source-timezone convention).
        if time_context_note:
            set_time_context_note(time_context_note)

        # 5. The agent registry + injected client factory. This is the SDK seam:
        #    the factory is supplied by the consumer (a MAF adapter, a stub, …);
        #    the facade imports no SDK.
        self.registry = AgentRegistry()
        self.registry.configure(_as_factory(agent_client), responses_client)

        # 6. Extend the generic SSE vocabulary with the consumer's raw-string
        #    domain events so the contract probe accepts them.
        if domain_events:
            register_domain_events(domain_events)
        self._domain_events = tuple(domain_events)

        # 7. Session store — injected, or the pure in-memory default (the
        #    zero-infra quickstart path). Domain seeding / durable warmup stay
        #    the consumer's concern.
        self.store = store if store is not None else InMemorySessionStore(
            default_agent_id=default_agent_id,
        )

        # Injection point for the consumer's per-request scope builder (K9).
        self.request_scope_builder = request_scope_builder
        self.tools = list(tools or [])

        logger.info(
            "AgentApp.initialised",
            extra={
                "control_dir": str(control_dir),
                "default_agent_id": default_agent_id or "<config>",
                "allowed_tool_prefixes": list(allowed_tool_prefixes),
                "domain_events": list(domain_events),
                "store": type(self.store).__name__,
            },
        )

    # ── Core run path ────────────────────────────────────────────────────────

    def _target_agent_id(self, agent_id: str | None) -> str:
        """Resolve the effective agent id (explicit → config default → fallback)."""
        if agent_id:
            return agent_id
        return _resolve_default_agent_id()

    async def _ensure_session_thread(self, session_id: str, agent_id: str) -> None:
        """Create the session + the agent's thread if they do not yet exist.

        The thread carries the agent's assembled system prompt as message 0 so a
        reloaded transcript shows the instructions the agent actually ran with.
        """
        session = await self.store.get(session_id)
        if session is None:
            session = SessionBase(id=session_id)
            await self.store.create(session)

        thread = await self.store.get_thread(session_id, agent_id)
        if thread is None:
            try:
                _id, display_name, system_prompt = get_prompt(agent_id)
            except Exception:
                # A missing/placeholder agent still gets a thread; the build()
                # call below raises the precise AgentNotFound if the id is bad.
                display_name, system_prompt = agent_id, ""
            await self.store.create_thread(
                session_id, agent_id, display_name, system_prompt=system_prompt,
            )

    async def chat(
        self,
        session_id: str,
        message: str,
        agent_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run one user→assistant turn and stream generic ``StreamEvent``s.

        The minimal-but-real run path: ensure the session + thread exist,
        persist the user message, build the agent via the registry (which uses
        the injected client factory), drive ``agent.run(message, stream=True)``,
        map each SDK update to ``StreamEvent``s via the domain-blind mapper,
        accumulate content + tool calls, persist the finalised assistant
        message, and close with a ``DONE`` event. On failure, a single ``ERROR``
        event is emitted and the assistant message is finalised as ``ERROR``.

        This is deliberately leaner than a full consumer turn (no revival loop,
        guardrails, abort registry, or LLMOps tracing — those stay the
        consumer's composition concern). It is the contract-faithful core that
        the quickstart needs and that a consumer can wrap.

        Args:
            session_id: Conversation id (created on first use).
            message: The user's input text.
            agent_id: Agent config key. ``None`` = config default / fallback.

        Yields:
            ``StreamEvent`` objects: ``TOKEN`` / ``TOOL_CALL_*`` / ``TOOL_RESULT``
            during the run, then a terminal ``DONE`` (or ``ERROR``).
        """
        target_id = self._target_agent_id(agent_id)
        await self._ensure_session_thread(session_id, target_id)

        # Persist the user message and a STREAMING assistant placeholder so a
        # mid-stream reload shows the turn in progress.
        user_msg = Message(role=Role.USER, content=message, agent_name=target_id)
        await self.store.append_message(session_id, user_msg, agent_id=target_id)
        assistant_msg = Message(
            role=Role.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            agent_name=target_id,
        )
        await self.store.append_message(session_id, assistant_msg, agent_id=target_id)

        buffer = ToolCallBuffer()
        usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}
        content_parts: list[str] = []
        tool_calls: dict[str, ToolCall] = {}

        try:
            agent = self.registry.build(target_id)
            async for update in agent.run(message, stream=True):
                for event in map_update_to_events(update, usage, call_buffer=buffer):
                    self._accumulate(event, content_parts, tool_calls)
                    yield event
            # Drain any tool call still open when the stream ends.
            for event in buffer.flush_open_calls():
                self._accumulate(event, content_parts, tool_calls)
                yield event

            assistant_msg.content = "".join(content_parts)
            assistant_msg.status = MessageStatus.COMPLETE
            assistant_msg.tool_calls = list(tool_calls.values())
            await self.store.update_message(session_id, assistant_msg, agent_id=target_id)

            yield StreamEvent(
                event=StreamEventType.DONE,
                data={
                    "assistant_message_id": assistant_msg.id,
                    "total_tokens": usage.get("total", 0),
                },
            )
        except Exception as exc:  # noqa: BLE001 — surfaced on the wire as ERROR
            logger.exception("AgentApp.chat.failed: session=%s agent=%s", session_id, target_id)
            assistant_msg.content = "".join(content_parts)
            assistant_msg.status = MessageStatus.ERROR
            assistant_msg.tool_calls = list(tool_calls.values())
            try:
                await self.store.update_message(session_id, assistant_msg, agent_id=target_id)
            except Exception:
                pass
            yield StreamEvent(
                event=StreamEventType.ERROR,
                data={"error_code": "internal_error", "message": str(exc)[:300]},
            )

    @staticmethod
    def _accumulate(
        event: StreamEvent,
        content_parts: list[str],
        tool_calls: dict[str, ToolCall],
    ) -> None:
        """Fold one streamed event into the assistant-message accumulators."""
        if event.event == StreamEventType.TOKEN:
            content_parts.append(str(event.data.get("token", "")))
        elif event.event == StreamEventType.TOOL_CALL_START:
            tc_id = str(event.data.get("id", ""))
            tool_calls[tc_id] = ToolCall(id=tc_id, name=str(event.data.get("name", "")))
        elif event.event == StreamEventType.TOOL_CALL_END:
            tc_id = str(event.data.get("id", ""))
            args = event.data.get("arguments", {})
            if tc_id in tool_calls:
                tool_calls[tc_id].arguments = args if isinstance(args, dict) else {}
            else:
                tool_calls[tc_id] = ToolCall(
                    id=tc_id,
                    name=str(event.data.get("name", "")),
                    arguments=args if isinstance(args, dict) else {},
                )
        elif event.event == StreamEventType.TOOL_RESULT:
            tc_id = str(event.data.get("id", ""))
            if tc_id in tool_calls:
                tool_calls[tc_id].result = str(event.data.get("result", ""))

    # ── FastAPI surface (the [fastapi] extra) ────────────────────────────────

    def router(self) -> Any:
        """Build a mountable FastAPI ``APIRouter`` exposing the agent.

        Routes (no prefix — the caller mounts under whatever path it wants):
            - ``POST /chat/{session_id}`` — body ``{"message": str, "agent_id"?:
              str}`` → ``text/event-stream`` of the generic SSE vocabulary.
            - ``GET  /sessions`` — list session summaries.

        ``fastapi`` / ``sse-starlette`` are imported here (the ``[fastapi]``
        extra) so the pure ``chat`` / example path never needs them.
        """
        from fastapi import APIRouter, Body
        from fastapi.responses import StreamingResponse

        from agentkit.hosting import format_sse_wire

        router = APIRouter()
        app_self = self

        @router.post("/chat/{session_id}")
        async def chat_endpoint(  # type: ignore[no-untyped-def]
            session_id: str,
            message: str = Body(..., embed=True),
            agent_id: str | None = Body(default=None, embed=True),
        ):
            async def event_stream() -> AsyncIterator[str]:
                async for event in app_self.chat(session_id, message, agent_id):
                    yield format_sse_wire(event)

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        @router.get("/sessions")
        async def list_sessions():  # type: ignore[no-untyped-def]
            summaries = await app_self.store.list_all()
            return [s.model_dump(mode="json") for s in summaries]

        return router

    def build_fastapi(self, *, prefix: str = "/api", title: str = "agentkit app") -> Any:
        """Build a FastAPI application with the agent router mounted.

        Separated from ``serve`` so a consumer can mount additional routers or
        middleware before running it.
        """
        from fastapi import FastAPI

        api = FastAPI(title=title)
        api.include_router(self.router(), prefix=prefix)
        return api

    def serve(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        prefix: str = "/api",
    ) -> None:
        """Run a uvicorn server exposing the agent — the quickstart entrypoint.

        Blocks. ``uvicorn`` is imported here so importing ``AgentApp`` (and the
        pure example) never requires it.
        """
        import uvicorn

        uvicorn.run(self.build_fastapi(prefix=prefix), host=host, port=port)


__all__ = ["AgentApp"]
