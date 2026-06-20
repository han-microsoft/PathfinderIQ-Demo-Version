# agentkit.app

The composition-root facade (Tier-1 capstone). `AgentApp` turns increments 1–8 into the project goal: *stand up a configured streaming agent, add tools, in a few lines.*

## Purpose
- Internalise the wiring a consumer's composition root would otherwise hand-assemble (settings registration, registry + injected client factory, fail-closed tool allowlist, control dir / fallback / time note, SSE vocabulary, session store) and expose three surfaces: `chat`, `router`, `serve`.

## Public API
`from agentkit.app import AgentApp, create_app`

### `create_app` — the quickstart one-liner
```python
create_app(
    *,
    config,                         # path to agent_config.yaml OR the control dir
    agent_client,                   # the ONLY SDK seam — () -> client factory (or instance)
    settings=None,                  # None → BaseAgentSettings.from_env() (local-dev default)
    tools_prefix=None,              # str | tuple → normalised to the allowed_tool_prefixes tuple
    store=None, default_agent_id=None, domain_events=(), tools=None,
    request_scope_builder=None, responses_client=None, time_context_note="",
) -> AgentApp
```
Thin additive wrapper over `AgentApp` that fills the two ergonomic gaps: default settings via `from_env`, and `tools_prefix` (single string or tuple) normalised to the fail-closed `allowed_tool_prefixes`. `AgentApp` itself is unchanged.

### Constructor
```python
AgentApp(
    settings,                       # BaseAgentSettings (or subclass) instance
    config,                         # path to agent_config.yaml OR the control dir
    tools=None,                     # optional; tools normally declared in YAML
    *,
    agent_client,                   # the ONLY SDK seam — a () -> client factory (or instance)
    store=None,                     # SessionStore; defaults to InMemorySessionStore
    request_scope_builder=None,     # K9 injection point (per-request scope)
    allowed_tool_prefixes=(),       # fail-closed import allowlist (consumer MUST set)
    default_agent_id="",            # fallback agent id
    domain_events=(),               # raw-string SSE event names to register
    responses_client=None,          # optional Responses-API client factory
    time_context_note="",           # optional source-tz note
)
```

### Methods
| Method | Signature | Does |
|---|---|---|
| `chat` | `async (session_id, message, agent_id=None) -> AsyncIterator[StreamEvent]` | the core run path: ensure session+thread → persist user msg → `registry.build` → `agent.run(stream=True)` → `map_update_to_events` → accumulate → persist assistant → terminal `DONE`/`ERROR` |
| `router` | `() -> fastapi.APIRouter` | `POST /chat/{sid}` (SSE) + `GET /sessions`; `[fastapi]` imported lazily |
| `build_fastapi` | `(*, prefix="/api", title=...) -> FastAPI` | app with the router mounted (mount more before serving) |
| `serve` | `(*, host="127.0.0.1", port=8000, prefix="/api") -> None` | uvicorn quickstart (blocks; `uvicorn` imported lazily) |

## Dependencies
- Within agentkit: `config`, `contracts`, `core`, `hosting`, `persistence`. No hard `agent_framework`/`fastapi`/`uvicorn` import at load.
- pip extra: base; `[fastapi]` (declared; also a base dep today) for `router`/`serve`.

## Injection seams (owns vs injects)
- **OWNS** — settings registration (`configure_settings`), the `AgentRegistry` + per-agent client cache, control-dir/fallback/allowlist/time-note config, the generic SSE vocabulary, and the **in-memory store default**.
- **INJECTS** — `agent_client` (factory; the only SDK seam), `store` (durable backend + two-phase warmup stays the consumer's), `request_scope_builder` (K9 stays the consumer's).
- **CONFIG-DRIVEN** — foundation prompts via the top-level `foundation_prompts:` YAML key, not a constructor arg.

## Extend recipe
- **Quickstart** → `AgentApp(settings, config=path, agent_client=StubFactory(), allowed_tool_prefixes=("mypkg.",), default_agent_id="x")` then `await app.chat(...)` or `app.serve()`. See `agentkit/examples/hello_agent/`.
- **Go from echo → real LLM** → swap `agent_client` for a `agentkit.sdk.maf_client`-backed factory; change nothing else.
- **Add an agent / tool** → edit the YAML (one block / one line); no facade change.

## Gotchas
- `allowed_tool_prefixes=()` (the default) forbids **every** tool import — a consumer MUST pass its own (e.g. `("tools.",)`), or every tool resolution fails-loud.
- Pass an explicit `settings` instance (e.g. `BaseAgentSettings(auth_enabled=False)`) so a quickstart doesn't read ambient `AUTH_ENABLED` from the shell and ValidationError.
- The registry caches one client per `agent_id` — pass a **factory** for multi-agent apps so each agent gets its own client (a bare instance is wrapped in a constant factory, fine for single-agent).
- `chat` is deliberately leaner than a full consumer turn — no revival loop, guardrails, abort registry, or LLMOps tracing (those stay the consumer's composition). GridIQ's production chat path is richer and is NOT routed through the facade.

## Zero-domain assertion
Imports `agentkit.*` only — zero consumer package, no SDK at load.
