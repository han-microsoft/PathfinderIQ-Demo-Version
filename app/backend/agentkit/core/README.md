# agentkit.core

The domain-blind agent orchestration runtime (K1–K8, K10). YAML-driven agent definitions, prompt loading, fail-closed tool resolution, SDK-agnostic agent construction, context providers, compaction, middleware, reflection.

## Purpose
- Turn a declarative `agent_config.yaml` (+ a `prompts/` dir) into built, tool-equipped agents — without importing any concrete LLM SDK or any consumer package.

## Public API
`from agentkit.core import ...`

### Seams / protocols
| Symbol | Kind | Does |
|---|---|---|
| `AgentClient` | Protocol | the SDK seam — `as_agent(...)` factory the consumer injects |
| `Tokenizer` | Protocol | token-count seam used by compaction |

### Registry + projections
| Symbol | Kind | Does |
|---|---|---|
| `AgentRegistry` | class | `configure(client_factory, ...)`, `build(agent_id)` (per-agent client cache), `list_definitions()` |
| `get_prompt` | fn | resolved system prompt for an agent |
| `list_definitions` | fn | agent definitions projection |

### Config loader (K1)
`load_agent_config`, `load_agents_block`, `find_agent`, `iter_agents`, `get_default_id`, `default_agent_id`, `resolve_agent_cfg`, `AgentNotFound`, `get_prompts_dir`, `get_control_dir`, `get_tool_display_names`, `invalidate_config_cache`, `invalidate_cache`, `set_default_control_dir`, `set_default_agent_fallback`.

### Tool resolver (K3 — fail-closed)
| Symbol | Kind | Does |
|---|---|---|
| `resolve_tool` / `resolve_tools` | fn | import `module:function` specs; `on_missing="raise"` (default) = **fail-loud** |
| `set_default_allowed_prefixes` | fn | set the import allowlist |
| `DEFAULT_ALLOWED_TOOL_PREFIXES` | const | `()` — **fail-closed**: empty forbids every import until the consumer sets prefixes |

### Prompts (K5)
`load_instructions`, `load_foundation_prompts`, `PromptLoadError`, `invalidate_foundation_prompt_cache`.

### Compaction / middleware / builder / reflection (K7/K8/K4/K10)
`TiktokenAdapter`, `create_compaction_strategy`, `create_middleware`, `build_agent`, `ReflectionController`.

### Agent build helpers (inc13b) — `agentkit.core.agent_builder`
`prepare_agent` (build/load one cached agent + inject per-request providers; consumer passes its registry, cache, middleware, user-memory container) and `get_reflection_settings`. Pure — no GridIQ import. Consumed by GridIQ's slimmed `agent_framework.py` facade. Pairs with `agentkit.hosting.run_engine.run_agent_stream`.

### Providers (K6) — `agentkit.core.providers`
`AgentRosterProvider`, `SystemTimeProvider`, `SessionHistoryProvider`, `CosmosUserMemoryProvider`, factory fns, `set_time_context_note`.

## Dependencies
- Within agentkit: `contracts`, `config`, `tokens`; lazily `agentkit.sdk.maf_client` (compaction/middleware delegate to it).
- pip extra: base. The SDK binding is the `[maf]` extra (see `agentkit.sdk`).

## Injection seams
- **`AgentClient`** — the consumer injects a client factory via `AgentRegistry.configure(...)`. Core never imports a concrete SDK.
- **Tool allowlist** — `set_default_allowed_prefixes(("tools.",))` (consumer-supplied). Empty = everything forbidden.
- **Control dir / fallback / time note** — `set_default_control_dir(path)`, `set_default_agent_fallback(id)`, `providers.set_time_context_note(note)`.

## Extend recipe
- **Add an agent** → one block in `agent_config.yaml` (`name`, `description`, `instructions: [x.md]`, `tools: [pkg.mod:fn]`). No code edit.
- **Add a tool to an agent** → one line under that agent's `tools:` (the spec must match an allowed prefix).
- **Swap the LLM SDK** → write a sibling `AgentClient` in `agentkit.sdk`; inject its factory. Core is unchanged.
- **Add a context provider** → implement the provider shape and register it in the provider factory; agents pick it up by config.

## Gotchas
- **Fail-closed + fail-loud (B-RESOLVER-SILENT).** `DEFAULT_ALLOWED_TOOL_PREFIXES=()` and `resolve_tools(on_missing="raise")`: an unknown tool spec **raises**, it does not silently skip. `on_missing="skip"` restores the old lenient behaviour explicitly.
- Core reads settings via `agentkit.config.get_settings()` — never `foundation.config`.
- Test monkeypatches target `agentkit.core.registry.{resolve_agent_cfg,build_agent}` and `agentkit.core.providers.time._simulated_time_setting`.

## Zero-domain assertion
Verified import-clean of every consumer package (static grep + runtime `walk_packages` probe). No SDK imported at module load.
