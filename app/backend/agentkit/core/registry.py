"""Agent registry (K2) — per-agent SDK client cache + builder façade.

Module role:
    Owns the stateful per-agent SDK client cache. Stateless config-derived
    projections (``get_prompt``, ``list_definitions``) are module-level free
    functions because they have no dependency on the registry's state.

Public surface:
    - AgentRegistry      — class; stateful client cache + build()
    - get_prompt         — pure, no client/factory dependency
    - list_definitions   — pure, returns API-shaped metadata

Layering:
    Imports ``agentkit.core`` siblings only. No GridIQ package, no concrete SDK
    (clients are injected via ``configure``). Was ``agent/registry.py``.
"""

from __future__ import annotations

import logging
from threading import RLock
from typing import Any

from agentkit.core.config_loader import (
    load_agents_block,
    invalidate_cache,
    get_default_id,
    iter_agents,
    resolve_agent_cfg,
    AgentNotFound,  # re-exported for callers that want to dispatch on it
)
from agentkit.core.builder import build_agent
from agentkit.core.prompt_loader import load_instructions

logger = logging.getLogger(__name__)


def _extract_agent_ui_metadata(agent_cfg: dict[str, Any]) -> dict[str, Any]:
    """Project optional UI metadata from an agent config block into API-safe fields.

    Args:
        agent_cfg: Raw agent definition from agent_config.yaml.

    Returns:
        Dict containing resolved asset URLs and optional product metadata.
    """
    ui_block = agent_cfg.get("ui", {}) if isinstance(agent_cfg.get("ui"), dict) else {}

    return {
        "headshot_url": None,
        "full_body_url": None,
        "product_summary": str(ui_block.get("product_summary", "")).strip() or None,
        "powered_by": [],
    }


# ── Stateless free functions ─────────────────────────────────────────────────


def get_prompt(agent_id: str | None = None) -> tuple[str, str, str]:
    """Load the assembled prompt text for an agent without building an SDK agent.

    Pure function over ``agent_config.yaml`` — no client, no factory, no registry
    instance required.

    Args:
        agent_id: Config key of the agent. ``None`` = use default.

    Returns:
        ``(agent_id, display_name, prompt_text)`` tuple.

    Raises:
        AgentNotFound: When ``agent_id`` is not present in the config.
    """
    from agentkit.core.config_loader import get_prompts_dir

    target_id, agent_cfg = resolve_agent_cfg(agent_id)

    prompts_dir = get_prompts_dir()
    instructions_spec = agent_cfg.get("instructions", [])
    prompt_text = load_instructions(instructions_spec, prompts_dir, None)
    display_name = agent_cfg.get("name", target_id)

    return target_id, display_name, prompt_text


def list_definitions() -> list[dict[str, Any]]:
    """Return metadata for all agents defined in agent_config.yaml.

    Returns:
        List of dicts with keys: id, name, description, tools, tool_count,
        is_default, surface, plus optional UI metadata fields.
    """
    config = load_agents_block()
    default_id = get_default_id(config)
    entries = iter_agents(config)

    result: list[dict[str, Any]] = []
    for agent_id, agent_cfg in entries:
        tools = list(agent_cfg.get("tools", []))
        ui_metadata = _extract_agent_ui_metadata(agent_cfg)
        result.append({
            "id": agent_id,
            "name": agent_cfg.get("name", agent_id),
            "description": (agent_cfg.get("description", "") or "").strip(),
            "tools": tools,
            "tool_count": len(tools),
            "is_default": agent_id == default_id,
            "surface": agent_cfg.get("surface", "chat"),
            **ui_metadata,
        })
    return result


# ── Stateful client cache + builder façade ───────────────────────────────────


class AgentRegistry:
    """Per-agent SDK client cache + ``build()`` façade.

    Each agent gets its own client instance to prevent identity bleed — the SDK
    client holds mutable state (agent_name, agent_id, _agent_definition) that
    persists across ``as_agent()`` calls. Sharing one client between agents
    causes whichever agent runs first to stamp its identity permanently.

    Call ``configure(client_factory, responses_client_factory)`` once at
    startup. The registry caches one client per agent_id for the process
    lifetime and serialises cache mutation so concurrent first builds do not
    orphan SDK transports.
    """

    def __init__(self) -> None:
        # Factory: () → agents-API client. Set by configure().
        self._client_factory: Any | None = None
        # Factory: () → Responses-API client. Set by configure().
        self._responses_client_factory: Any | None = None
        # Per-agent client cache: agent_id → client instance.
        self._clients: dict[str, Any] = {}
        self._clients_lock = RLock()

    def configure(self, client_factory: Any, responses_client_factory: Any | None = None) -> None:
        """Register the client factories. Called once at startup."""
        with self._clients_lock:
            self._close_cached_clients_locked()
            self._client_factory = client_factory
            self._responses_client_factory = responses_client_factory
        logger.info("AgentRegistry configured with client factory")

    def _close_cached_clients_locked(self) -> None:
        """Best-effort close before dropping cached SDK clients."""
        for agent_id, client in list(self._clients.items()):
            close = getattr(client, "close", None)
            if close is None:
                close = getattr(client, "aclose", None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, "close"):
                    result.close()
            except Exception:
                logger.warning("agent_registry.client.close_failed: agent=%s", agent_id, exc_info=True)
        self._clients.clear()

    def _get_client(self, agent_id: str, agent_cfg: dict | None = None) -> Any:
        """Return the cached client for ``agent_id``; create it on first call.

        Client type chosen from ``agent_cfg["client_type"]``:
            - ``"responses"`` → Responses-API client (supports WebSearchTool)
            - default        → agents-API client
        """
        with self._clients_lock:
            if agent_id in self._clients:
                return self._clients[agent_id]

            client_type = (agent_cfg or {}).get("client_type", "agents")

            if client_type == "responses":
                if self._responses_client_factory is None:
                    raise RuntimeError(
                        f"Agent '{agent_id}' requires client_type='responses' but "
                        "no responses_client_factory was configured."
                    )
                client = self._responses_client_factory()
                logger.info("Created Responses API client for agent '%s'", agent_id)
            else:
                if self._client_factory is None:
                    raise RuntimeError(
                        "AgentRegistry not configured — call registry.configure(client_factory) "
                        "at startup. Is LLM_PROVIDER=agent?"
                    )
                client = self._client_factory()
                logger.info("Created Agents API client for agent '%s'", agent_id)

            self._clients[agent_id] = client
            return client

    def build(
        self,
        agent_id: str | None,
        client: Any = None,
        *,
        model_override: str = "",
        middleware: Any | None = None,
        context_providers: Any | None = None,
    ) -> Any:
        """Build an SDK Agent by ID using the per-agent dedicated client.

        Args:
            agent_id: Config key. ``None`` = default agent.
            client: Explicit override (used by tests / non-cached callers).
            model_override: From the retry/fallback loop. Empty = config default.
            middleware: SDK middleware instances forwarded to ``client.as_agent()``.
            context_providers: Context provider instances.

        Raises:
            AgentNotFound: When ``agent_id`` is not in agent_config.yaml.
        """
        from agentkit.core.config_loader import get_prompts_dir

        target_id, agent_cfg = resolve_agent_cfg(agent_id)

        prompts_dir = get_prompts_dir()
        if not prompts_dir:
            raise ValueError(
                "Prompts directory not found. "
                "Check control/agent_config.yaml prompts_dir setting."
            )

        # Use the per-agent dedicated client (prevents identity bleed). If a
        # client was explicitly passed (tests / back-compat) use that.
        effective_client = client if client is not None else self._get_client(target_id, agent_cfg)

        # The SDK stores function-invocation config on the client, so the
        # per-agent value must be applied only for the duration of this build.
        with self._clients_lock:
            invocation_config = getattr(effective_client, "function_invocation_configuration", None)
            previous_max_iters = None
            had_previous_max_iters = False
            agent_max_iters = agent_cfg.get("max_iterations")
            if agent_max_iters is not None and isinstance(invocation_config, dict):
                had_previous_max_iters = "max_iterations" in invocation_config
                previous_max_iters = invocation_config.get("max_iterations")
                invocation_config["max_iterations"] = int(agent_max_iters)
                logger.info("Agent '%s': max_iterations=%d", target_id, agent_max_iters)
            try:
                return build_agent(
                    target_id, agent_cfg, prompts_dir, None, effective_client,
                    model_override=model_override,
                    middleware=middleware, context_providers=context_providers,
                )
            finally:
                if agent_max_iters is not None and isinstance(invocation_config, dict):
                    if had_previous_max_iters:
                        invocation_config["max_iterations"] = previous_max_iters
                    else:
                        invocation_config.pop("max_iterations", None)

    def invalidate_clients(self) -> None:
        """Clear both the YAML config cache AND the per-agent SDK client cache."""
        invalidate_cache()
        with self._clients_lock:
            self._close_cached_clients_locked()


__all__ = [
    "AgentRegistry",
    "get_prompt",
    "list_definitions",
    "AgentNotFound",
]
