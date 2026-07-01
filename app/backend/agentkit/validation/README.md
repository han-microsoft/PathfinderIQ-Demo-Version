# agentkit.validation

Input shape-gates + the per-request tool-call ledger. Stdlib only.

## Purpose
- One home for cross-cutting input validators (string-shape gates) that previously lived inline in N routers.
- A per-request semantic tool-call ledger (`tool_guard`) so a tool runs at most once per logical request when required.

## Public API
`from agentkit.validation import ...`

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `validate_station` | fn | `(value: str\|None) -> str\|None` | matches `^[A-Za-z0-9_]{1,32}$`; `None`/`""` pass through as `None`; else `ValueError` |
| `require_station` | fn | `(value, *, allow_empty=True) -> str\|None` | as above; `allow_empty=False` raises on missing |
| `validate_session_id` | fn | `(value: str) -> str` | bounded id (`SESSION_ID_MAX_LEN=64`); else `ValueError` |
| `STATION_RE` | regex | `^[A-Za-z0-9_]{1,32}$` | the shared shape constant |
| `SESSION_ID_MAX_LEN` | int | `64` | session-id cap |
| `set_tool_call_ledger` | fn | `(...) -> ...` | bind a per-request contextvar ledger |
| `reset_tool_call_ledger` | fn | `(...) -> None` | clear/restore the ledger |
| `record_tool_call_once` | fn | `(...) -> bool` | record a call; returns whether it is the first this request |

> Naming: `validate_station`/`require_station`/`STATION_RE` are **generic string-shape gates** — "station" here is the historic name of a `^[A-Za-z0-9_]{1,32}$` token validator, not domain knowledge. Use them for any short identifier.

## Dependencies
- Within agentkit: `agentkit.validation.tool_guard` (re-exported here).
- pip extra: none (stdlib + contextvars).

## Injection seams
None. The ledger is set/reset by the consumer's request middleware.

## Extend recipe
- **Add a shape gate** → add a `validate_X(value) -> value` raising `ValueError`; export in `__all__`. The consumer's router boundary translates `ValueError` to 422/404.
- **Guard a tool to once-per-request** → in the tool body, `if not record_tool_call_once(key): return cached`.

## Gotchas
- Validators raise `ValueError` — they do **not** raise `HTTPException` (that couples to FastAPI). The router boundary maps it.
- `tool_guard` is contextvar-based; tests patch `agentkit.validation.tool_guard.*` and must `reset_tool_call_ledger` between requests.

## Zero-domain assertion
Imports no consumer package. "station" is a generic identifier shape, not domain content.
