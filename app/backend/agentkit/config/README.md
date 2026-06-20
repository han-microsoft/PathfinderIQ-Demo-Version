# agentkit.config

Settings base + per-request scope carrier. The "resolve config once, freeze, distribute a snapshot" layer.

## Purpose
- `BaseAgentSettings` — the domain-blind half of a consumer's settings (LLM provider, agent knobs, context window, session persistence, auth, CORS, observability, SSE tuning). Consumers subclass to add domain fields.
- The process-wide settings accessor (`get_settings`/`configure_settings`) so agentkit internals read config without importing a consumer package.
- `RequestScope` — a frozen per-request snapshot with opaque `services`/`bindings` bags the consumer fills.

## Public API
`from agentkit.config import ...`

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `BaseAgentSettings` | class | `BaseSettings` subclass | generic settings; `env_prefix=""` (bare env names), `extra="ignore"` |
| `BaseAgentSettings.from_env` | classmethod | `(**overrides) -> BaseAgentSettings` | build from env with overrides applied **correctly** — `validation_alias`-only fields (which silently ignore kwargs) are routed through their env alias (set → build → restore). Does not register; pair with `configure_settings(...)`. |
| `get_settings` | fn | `() -> BaseAgentSettings` | the registered instance; lazily builds a bare default if none registered |
| `configure_settings` | fn | `(instance) -> None` | register the process-wide singleton (composition root calls once) |
| `running_in_azure` | fn | `() -> bool` | platform sensor (reads `WEBSITE_*`/container env) |
| `RequestScope` | dataclass | frozen | `scope_name/llm_model/session_id/config/prompts_dir/services/bindings/settings` |
| `configure_scope_fallback` | fn | `(builder: Callable[[], RequestScope]) -> None` | register a default-scope builder for non-request contexts |
| `get_request_scope` | fn | `() -> RequestScope` | read the contextvar-bound scope (or fallback) |
| `set_request_scope` / `reset_request_scope` | fn | `(scope)->Token` / `(token)->None` | bind/unbind per request |
| `get_session_id` / `set_session_id` / `reset_session_id` | fn | contextvar session-id accessors | |

Key `BaseAgentSettings` fields (all `ge`/`le`-safe defaults, local-dev-safe): `llm_provider`, `llm_model`, `llm_base_url`, `llm_api_key`, `max_context_tokens`, `max_response_tokens`, `auth_enabled`, `cors_origins`, `otel_export_target`, `chat_timeout_seconds`, `max_sse_frame_bytes`, `cosmos_session_endpoint`, `llmops_backend`, `dev_public_key_ed25519`, …

## Dependencies
- Within agentkit: none (depends only on stdlib + pydantic/pydantic-settings).
- pip extra: none (base).

## Injection seams
- **Settings registration** — the composition root calls `configure_settings(MySettings())`. Every agentkit internal reads `get_settings()`.
- **Scope fallback builder** — `configure_scope_fallback(lambda: RequestScope(...))` so off-request code (warmups, tests) gets a sane default.
- The consumer's `request_scope_builder` (K9) fills `services`/`bindings` with its domain configs — agentkit only carries the opaque bags.

## Extend recipe
- **Add a domain config field** → subclass `BaseAgentSettings`, add the field, `configure_settings(MySettings())` at import. Generic fields resolve from the base.
- **Carry a domain service per request** → put it under `RequestScope.services["myservice"]`; the agentkit datasource adaptors read it only through an injected resolver, never directly.

## Gotchas
- **`get_settings()` lazy-bare-build trap** — with no registered settings it builds a bare `BaseAgentSettings()`, which ValidationErrors on required fields in an isolated test. In settings tests save/restore the raw module global `agentkit.config.settings._active_settings` around `configure_settings(...)`; do **not** call `get_settings()` to snapshot it.
- **`validation_alias`-only fields** (e.g. `llmops_backend = Field(validation_alias=AliasChoices("LLMOPS_BACKEND"))`, no `populate_by_name`) can be set **only** via the env-var alias. `monkeypatch.setenv("LLMOPS_BACKEND", ...)` — a `llmops_backend=...` kwarg is silently ignored.
- Init kwargs beat env in pydantic-settings — pass `auth_enabled=False` explicitly to make a quickstart env-independent.

## Zero-domain assertion
Imports no consumer package. The carrier's `services`/`bindings` are opaque — no domain types named here.

## agent_config.yaml schema

The declarative agent surface. Loaded by [`agentkit.core.config_loader`](../core/config_loader.py) + [`agentkit.core.prompt_loader`](../core/prompt_loader.py) + [`agentkit.core.registry`](../core/registry.py) + [`agentkit.core.builder`](../core/builder.py) + [`agentkit.core.agent_builder`](../core/agent_builder.py) (the file lives in the consumer's *control* directory, not in agentkit). The keys below are the **only** ones the loaders actually read — no others are consumed.

### Top-level keys

| Key | Type | Read by | Meaning |
|---|---|---|---|
| `agents` | mapping | `config_loader.load_agents_block` | **Required.** The agent block (reserved keys + per-agent definitions, below). |
| `prompts_dir` | str | `config_loader.get_prompts_dir` | Prompts directory, resolved relative to the control dir. Default `"prompts"`. |
| `foundation_prompts` | list[str] | `prompt_loader.load_foundation_prompts` | Shared-knowledge prompt filenames (relative to `prompts_dir`) prepended to every agent's instructions. |
| `tool_display_names` | mapping[str,str] | `config_loader.get_tool_display_names` | Optional `function_name → human label` map for a chat UI. |

### Inside `agents:`

| Key | Type | Meaning |
|---|---|---|
| `default` | str | *Reserved.* The default agent id (used when `chat` is called without an `agent_id`). Falls back to the consumer-registered fallback when absent. |
| `mode` | — | *Reserved.* Skipped by the agent iterator; not an agent definition. |
| *(any other key)* | mapping | A **per-agent definition** (id → config, below). |

### Per-agent definition (`agents.<id>`)

| Key | Type | Read by | Meaning |
|---|---|---|---|
| `name` | str | `registry`, `builder` | Display name. Defaults to the agent id. |
| `description` | str | `registry`, `builder` | One-line description. |
| `instructions` | list[str] | `registry`, `builder` | Prompt filenames (relative to `prompts_dir`) concatenated into the system prompt. |
| `tools` | list[str] | `registry`, `builder` | Tool specs as `module:function`; each module must sit under an `allowed_tool_prefixes` entry (fail-closed). |
| `model` | str | `builder` | Model-deployment override; falls back to `settings.llm_model`. |
| `surface` | str | `registry` | UI surface tag. Default `"chat"`. |
| `client_type` | str | `registry` | Client kind — `"agents"` (default) or `"responses"`. |
| `reflection` | bool | `agent_builder` | Enable the reflection loop. Default `false`. |
| `max_reflection_rounds` | int | `agent_builder` | Reflection-round cap. Default `2`. |
| `max_iterations` | int | `registry` | Per-agent tool-iteration cap (SDK invocation config). |
| `ui` | mapping | `registry` | Optional per-agent UI metadata block. |

> Guardrails are **not** an `agent_config.yaml` key — they are resolved by name from the consumer's own config via `agentkit.guardrails.resolve_guardrails`, not from this file.

Minimal valid example:

```yaml
agents:
  default: hello
  hello:
    name: HelloAgent
    description: "A neutral echo agent."
    instructions:
      - hello.md
    tools:
      - agentkit.examples.hello_agent.echo_tool:echo
```
