"""agentkit.core — domain-blind agent orchestration runtime (K1–K8, K10).

Lifted from GridIQ's ``agent/`` package (Tier-1 extraction increment 6). Owns
YAML-driven agent definition parsing (config_loader), prompt loading
(prompt_loader), tool resolution (tool_resolver), SDK agent construction
(builder + registry), context providers (providers/), compaction (compaction),
middleware (middleware), and the optional reflection loop (reflection).

SDK isolation:
    The concrete Microsoft Agent Framework binding lives in
    ``agentkit.sdk.maf_client``; ``builder`` accepts any object satisfying
    ``core.AgentClient`` (the consumer's composition root injects one). Core
    imports no GridIQ package and no SDK at import time.

Consumer configuration (call once at composition time):
    - ``config_loader.set_default_control_dir(<path>)`` — where agent_config.yaml lives.
    - ``config_loader.set_default_agent_fallback(<id>)`` — fallback when config omits ``default``.
    - ``tool_resolver.set_default_allowed_prefixes((...))`` — fail-closed import allowlist.
    - ``providers.set_time_context_note(<note>)`` — optional domain time note.
"""

from agentkit.core._protocols import AgentClient, Tokenizer
from agentkit.core.registry import AgentRegistry, get_prompt, list_definitions
from agentkit.core.config_loader import (
    load_agent_config,
    load_agents_block,
    find_agent,
    iter_agents,
    get_default_id,
    default_agent_id,
    resolve_agent_cfg,
    AgentNotFound,
    get_prompts_dir,
    get_control_dir,
    get_tool_display_names,
    invalidate_config_cache,
    invalidate_cache,
    set_default_control_dir,
    set_default_agent_fallback,
)
from agentkit.core.tool_resolver import (
    resolve_tool,
    resolve_tools,
    set_default_allowed_prefixes,
    DEFAULT_ALLOWED_TOOL_PREFIXES,
)
from agentkit.core.prompt_loader import (
    load_instructions,
    load_foundation_prompts,
    PromptLoadError,
    invalidate_foundation_prompt_cache,
)
from agentkit.core.compaction import TiktokenAdapter, create_compaction_strategy
from agentkit.core.middleware import create_middleware
from agentkit.core.builder import build_agent
from agentkit.core.reflection import ReflectionController
from agentkit.core.agent_builder import get_reflection_settings, prepare_agent

__all__ = [
    # protocols / seams
    "AgentClient",
    "Tokenizer",
    # registry + projections
    "AgentRegistry",
    "get_prompt",
    "list_definitions",
    # config loader
    "load_agent_config",
    "load_agents_block",
    "find_agent",
    "iter_agents",
    "get_default_id",
    "default_agent_id",
    "resolve_agent_cfg",
    "AgentNotFound",
    "get_prompts_dir",
    "get_control_dir",
    "get_tool_display_names",
    "invalidate_config_cache",
    "invalidate_cache",
    "set_default_control_dir",
    "set_default_agent_fallback",
    # tool resolver
    "resolve_tool",
    "resolve_tools",
    "set_default_allowed_prefixes",
    "DEFAULT_ALLOWED_TOOL_PREFIXES",
    # prompts
    "load_instructions",
    "load_foundation_prompts",
    "PromptLoadError",
    "invalidate_foundation_prompt_cache",
    # compaction / middleware / builder / reflection
    "TiktokenAdapter",
    "create_compaction_strategy",
    "create_middleware",
    "build_agent",
    "ReflectionController",
    "get_reflection_settings",
    "prepare_agent",
]
