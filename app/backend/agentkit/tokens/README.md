# agentkit.tokens

tiktoken-based token counter.

## Purpose
- A single `count_tokens(text)` used by compaction and context-budgeting. Encoder selection follows the active model; lazy so importing the module pays no setup cost.

## Public API
`from agentkit.tokens import count_tokens`

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `count_tokens` | fn | `(text: str) -> int` | token count via tiktoken; `""` → `0`. Encoder built on first call from `get_settings().llm_model`, falling back to `cl100k_base` for unknown models. |

## Dependencies
- Within agentkit: `agentkit.config.get_settings` (model selection).
- pip extra: **`[tokens]`** (`tiktoken`). See note below.

## Injection seams
None. Model name comes from the registered settings.

## Extend recipe
- **Budget context** → `if count_tokens(candidate) > budget: drop/compact`. `agentkit.core.compaction.TiktokenAdapter` already wraps this for the runtime.

## Gotchas
- The encoder is a module-global initialised on first `count_tokens` call — the first call pays setup cost; later calls are cheap.
- **Extra:** `pyproject.toml` declares `[tokens]` (`tiktoken>=0.7.0`). It is also a hard base dependency of GridIQ today; a standalone consumer installs `agentkit[tokens]`.

## Zero-domain assertion
Imports no consumer package. No domain vocabulary.
