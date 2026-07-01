# agentkit.hosting

The generic SSE transport spine (S1/S2/S4) + the runtime providers/channel. Domain-blind: imports `agentkit.contracts`, `agentkit.config`, stdlib (+ `fastapi`/`sse-starlette` lazily). The `[fastapi]` layer.

## Purpose
- Format SSE frames, own the generic event vocabulary (and let consumers register domain event names on top), map SDK update objects → `StreamEvent`s, run a single-flight abort registry, and provide a headless live-contract probe core.
- `sse/` sub-package adds the keepalive/accumulation wrapper + disconnect-aware producer; `runtime/` adds a bounded (visible-overflow) channel + reference Echo/Mock LLM providers; `devauth/` adds generic Ed25519 signed-request dev auth (domain-blind, injected `identity_factory`).

## Public API
`from agentkit.hosting import ...`

| Symbol | Kind | Does |
|---|---|---|
| `format_sse` / `format_sse_wire` | fn | format a `StreamEvent` as an SSE frame; frame-size cap via `get_settings().max_sse_frame_bytes` |
| `GENERIC_EVENT_NAMES` / `GENERIC_TERMINALS` | frozenset | the generic vocabulary (`StreamEventType` values) + terminal set |
| `register_domain_events` | fn | add raw-string domain event names to the known vocabulary |
| `known_event_names` / `is_known_event` | fn | the union (generic ∪ registered); the probe's allowlist |
| `ToolCallBuffer` | class | accumulate streamed tool-call deltas; `flush_open_calls()` |
| `map_update_to_events` | fn | SDK-blind (duck-typed) update → `StreamEvent`s |
| `extract_usage` / `extract_user_message` | fn | pull token usage / user text from an update |
| `abort_events` | obj | abort registry |
| `try_register_abort_event` / `register_abort_event` / `unregister_abort_event` / `cleanup_stale_entries` | fn | single-flight abort lifecycle |
| `parse_sse_frames` / `check_event_sequence` | fn | live-contract probe core |

### Submodules (import directly)
| Module | Symbols |
|---|---|
| `agentkit.hosting.run_engine` | `run_agent_stream` — the full SDK-agnostic streaming run loop (main run + retry/fallback/stall-revival + reflection + completion-check + empty-fallback + metadata/DONE). Consumers inject `agent_factory`, `is_update`, `build_revival`, `completion_agent_resolver`, `cost_estimator`, `tool_call_buffer_factory`. |
| `agentkit.hosting.run_loop` | `RunProgress`, `Run*` terminal dataclasses, `AgentRunAbortedError`, `AgentRunStalledError`, `iter_updates_with_stall_timeout`, `record_run_progress` |
| `agentkit.hosting.completion` | `COMPLETION_CHECK_SENTINEL` + completion-check helpers |
| `agentkit.hosting.sse.service` | `wrap_stream_with_keepalive`, `accumulate_stream_event`, `ConversationTurnProtocol` |
| `agentkit.hosting.sse.disconnect` | `sse_with_disconnect`, `DisconnectAware` |
| `agentkit.hosting.devauth` | `install_signed_request_auth`, `SignedRequestASGIMiddleware`, `ReplayCache`, `verify`, `VerifyResult` — generic Ed25519 signed-request dev auth; injects `identity_factory(slug)→principal` so agentkit never imports a domain identity type (see [devauth/README.md](devauth/README.md)). |
| `agentkit.hosting.runtime.bounded_channel` | `BoundedEventChannel`, `DEFAULT_OVERFLOW_MARKER_INTERVAL_SECONDS` |
| `agentkit.hosting.runtime.providers` | `EchoLLMService`, `MockLLMService` |

## Dependencies
- Within agentkit: `contracts`, `config`.
- pip extra: **`[fastapi]`** (`fastapi`, `uvicorn[standard]`, `sse-starlette` — imported lazily). Declared in `pyproject.toml`; also hard base deps of GridIQ today.

## Injection seams
- **Domain event vocabulary** — `register_domain_events(("audit_report", "situation", ...))` from the consumer; agentkit ships only the generic enum.
- **Conversation turn / request** — `service`/`disconnect` consume the turn + request **structurally** (`ConversationTurnProtocol` / `DisconnectAware` duck-typed) so agentkit imports zero consumer types.

## Extend recipe
- **Add a domain SSE event** → `register_domain_events((...))` in your consumer (GridIQ: `hosting/fastapi/streaming/domain_events.py`). Never add it to the agentkit enum.
- **Map a new SDK's updates** → `map_update_to_events` is duck-typed; if a new SDK shapes updates differently, extend the mapper (it reads `text`/`author_name`/`contents`-style attrs).

## Gotchas
- **SSE order contract is the teeth.** `check_event_sequence(allowed_events=None)` defaults to `known_event_names()`; an **unregistered** event name on the wire = contract FAILURE. Exactly one terminal frame, no frame after it, every `TOOL_CALL_END.id` has a prior `TOOL_CALL_START.id`.
- **B-CHAOS-025**: the abort registry is an in-process dict — single-replica only. A `# TODO(B-CHAOS-025)` marks the distributed-lease seam for multi-replica.
- **Bounded channel overflow is visible**: `BoundedEventChannel` emits an overflow marker rather than silently dropping; the marker `put_nowait`s on the same full queue, so single-threaded it only lands once a consumer concurrently drains.
- Settings side-effect: the old GridIQ `streaming/sse.py` triggered `configure_settings` at import; the agentkit module uses `get_settings()`. In isolated tests, ensure settings are registered or `format_sse` ValidationErrors on a bare build.

## Zero-domain assertion
Imports no consumer package — only stale docstring mentions, zero import statements. The vocabulary split keeps domain event names consumer-side.
