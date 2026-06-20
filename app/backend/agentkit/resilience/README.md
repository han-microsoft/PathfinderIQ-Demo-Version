# agentkit.resilience

Circuit breaker + retry classification + model-fallback queue. Pure stdlib resilience primitives.

## Purpose
- A thread-safe `CircuitBreaker` (Closed→Open→Half-Open) and a process-wide `CircuitBreakerRegistry` singleton for health reporting.
- Retry-decision helpers (transient vs fatal, rate-limit detection, `Retry-After` parsing).
- A model-fallback queue so the LLM layer can degrade to alternate deployments.

## Public API
`from agentkit.resilience import ...` (the module has no `__all__`; these are the public names)

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `CircuitBreaker` | class | `(name, failure_threshold=3, cooldown_secs=60, max_cooldown_secs=300)` | thread-safe breaker; `is_open()/record_success()/record_failure()` |
| `CircuitBreakerRegistry` | class | — | `get_or_create(name, **kw)`, `all_statuses()` |
| `registry` | singleton | `CircuitBreakerRegistry` | process-wide; same instance everywhere imported |
| `CircuitState` | enum | `closed/open/half-open` | |
| `DependencyStatus` | enum | `up/down/degraded/throttled/not_configured` | unified health for `/health` |
| `should_retry` | fn | `(exc, attempt, max_attempts) -> bool` | retry decision |
| `is_transient` / `is_fatal` / `is_rate_limit` | fn | `(exc) -> bool` | exception classification |
| `parse_retry_seconds` | fn | `(exc) -> float \| None` | extract `Retry-After` |
| `log_retry` | fn | structured retry log | |
| `get_model_fallback_queue` | fn | `() -> ...` | ordered fallback deployments from `get_settings().llm_fallback_models` |

## Dependencies
- Within agentkit: `agentkit.config.get_settings` (fallback queue reads `llm_fallback_models`).
- pip extra: none (stdlib + pydantic via config).

## Injection seams
None. Each external dependency registers its own breaker via `registry.get_or_create(name)`; call sites decide the fallback behaviour when open.

## Extend recipe
- **Protect a new external call** → `b = registry.get_or_create("my_service", failure_threshold=5, cooldown_secs=60)`; gate with `if b.is_open(): return degraded_envelope(...)`, then `record_success()/record_failure()`.
- **Add a fallback model** → set `LLM_FALLBACK_MODELS` (CSV) in env; `get_model_fallback_queue()` picks it up.

## Gotchas
- `registry` is a singleton — health endpoints read `registry.all_statuses()`; do not instantiate a second registry.
- The breaker uses `threading.Lock` (not asyncio) on purpose — works from both sync `to_thread` and async contexts; there are no await points inside the lock.
- This module owns the state machine only — **not** retry loops, fallback behaviour, or concurrency limits (those are the caller's).

## Zero-domain assertion
Imports no consumer package. No domain vocabulary.
