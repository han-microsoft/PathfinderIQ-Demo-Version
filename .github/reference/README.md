# reference — patterns + worked examples

"What good looks like." Language-agnostic patterns (PATTERNS.md) plus
self-contained, self-proving example modules lifted from real production
agentkits and edited for clarity + independence.

## How to use

- **Read, don't blind-copy.** These are exemplars of shape and discipline, not a
  library to vendor. Lift the pattern; rewrite for your context.
- Patterns transcend language. Examples are Python (the convergent source), but
  each pattern's *principle* applies anywhere.
- Each example is **standalone** (zero cross-imports, stdlib-only) and
  **self-proving** (`python3 <file>` runs an inline demo + asserts). That is the
  bar: if an example can't prove itself, it isn't a reference.

## Contents

| File | Pattern | Seed tenet |
| --- | --- | --- |
| [PATTERNS.md](PATTERNS.md) | All 8 patterns, language-agnostic | Law 1, P1, P2, T4 |
| [python/error_envelope.py](python/error_envelope.py) | Error chokepoint: one sanitizer, never leak | T4, safety |
| [python/circuit_breaker.py](python/circuit_breaker.py) | Resilience state machine, thread-safe | P2 |
| [python/request_scope.py](python/request_scope.py) | Contextvar request scope, fallback-injected | P1, P2 |
| [python/duck_typed_adapter.py](python/duck_typed_adapter.py) | Read foreign objects without importing the SDK | P2 |
| [python/sse_stream/](python/sse_stream/) | Streaming agent -> SSE spine (multi-module): event contract, tool aggregation, stall, abort | P1, P2, T4, P7 |

## Provenance

Lifted + simplified from two independently-built agentkits that converged on
byte-identical versions of these patterns — the strongest reuse signal there is.
Domain vocabulary, framework coupling, and heavy deps removed so each example
stands alone and runs under the seed's zero-dep rule.
