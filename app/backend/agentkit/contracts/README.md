# agentkit.contracts

Wire/boundary types shared across every consumer and every other agentkit layer. The innermost ring of the dependency DAG — imports stdlib + pydantic only.

## Purpose
- The canonical conversation/wire pydantic models, the structured error taxonomy, and the tool error envelope.
- Single source of truth for the SSE event vocabulary (`StreamEventType`) and the generic session shape (`SessionBase`).

## Public API

Package `__init__` re-exports **nothing** — import from the submodule.

### `agentkit.contracts.envelope`
| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `error_envelope` | fn | `(detail: str, *, exc: BaseException \| None=None) -> str` | `{"error": true, "detail": "<sanitised>"}` JSON. Caps detail at 500 chars, strips absolute URLs (`<redacted-url>`). |
| `degraded_envelope` | fn | `(detail: str) -> str` | `{"degraded": true, "detail": ...}` — reduced-fidelity answer, not a failure. |
| `from_value_error` | fn | `(exc: ValueError) -> str` | Wrap a validator `ValueError` message verbatim (sanitised) in an error envelope. |

### `agentkit.contracts.models`
| Symbol | Kind | Notes |
|---|---|---|
| `Role` | enum | `system/user/assistant/tool` |
| `MessageStatus` | enum | `pending→streaming→complete\|error\|aborted` |
| `AgentRunStatus` | enum | background-run lifecycle |
| `StreamEventType` | enum | the SSE event vocabulary (token, tool_call_*, done, error, aborted, keepalive, delegation_*, background_*) |
| `ToolCall` | model | `id/name/arguments/result/duration_ms` |
| `ContextSnapshot` | model | record of what context was sent to the LLM |
| `Message` | model | one conversation message |
| `AgentThread` | model | per-agent thread of messages |
| `BackgroundAgentRun` | model | durable background-run record |
| `SessionBase` | model | **generic session shape (schema v3)** — subclass to add domain state |
| `SessionSummaryBase` | model | list-view metadata (counts, no messages) |
| `StreamEvent` | model | `{event: StreamEventType, data: dict}` — the SSE wire envelope |
| `StreamMetadata` | model | final METADATA event payload |
| `migrate_v2_to_v3` | fn | `(data: dict) -> dict` — flat `messages[]` → per-agent `threads{}`; runs inside `SessionBase`'s validator |

### `agentkit.contracts.errors`
| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `ErrorCode` | enum | — | client-dispatchable error classes (`content_filtered/tool_timeout/tool_error/provider_error/auth_error/timeout/internal_error`) |
| `classify_error` | fn | `(exc: Exception) -> tuple[ErrorCode, str]` | exception → code + **client-safe** message (no raw text / URLs / stack) |
| `make_error_event` | fn | `(code, message, *, error_id="", retry_after=None, tool_name=None) -> StreamEvent` | build an `ERROR` `StreamEvent` |
| `generate_error_id` | fn | `() -> str` | 12-char hex correlation id |

## Dependencies
- Within agentkit: none (this is the base ring). `errors` imports `models`.
- pip extra: none — pydantic is a base dependency.

## Injection seams
None. Pure data/contracts. Consumers subclass `SessionBase`/`SessionSummaryBase` to add domain fields; they inherit the v2→v3 migration validator for free.

## Extend recipe
- **Add a generic SSE event type** → add a member to `StreamEventType` (it auto-joins `GENERIC_EVENT_NAMES` in `agentkit.hosting`). Domain-specific raw-string events go through `register_domain_events`, **not** here.
- **Add a session field for your domain** → subclass `SessionBase` in your consumer package; never edit the base.

## Gotchas
- **`ToolCall.duration_ms` is load-bearing.** A prior extraction dropped it during a hand-recreation; the post-tool duration stamp then raised `ValueError: object has no field "duration_ms"`, surfaced as `event: error internal_error` only after a tool result. When editing models, field-diff old-vs-new before shipping.
- `SessionBase.etag` is `exclude=True` — never crosses the wire or persists; a durable backend populates it from `get`.
- `classify_error` messages are intentionally generic — do not enrich them with exception text (that re-introduces the leak it removes).

## Zero-domain assertion
Imports no consumer package. No station codes / equipment ids / CIM vocabulary.
