# agentkit.guardrails

Provider-agnostic input/output AI-safety chain. Pure `pydantic` + stdlib at the protocol level; concrete checks use `httpx` + `azure.identity` (all base deps — no new pip extra).

## Purpose
- Define the `InputGuardrail`/`OutputGuardrail` Protocols + verdict types, a name→class registry, a fail-open runner, and concrete checks (content safety, prompt-shield, input length, PII filter).

## Public API
`from agentkit.guardrails import ...`

| Symbol | Kind | Does |
|---|---|---|
| `GuardrailVerdict` | enum | `pass/warn/block` |
| `GuardrailResult` | model | `verdict/guardrail_name/reason/metadata` |
| `InputGuardrail` | Protocol | `name`; `async check(input_text) -> GuardrailResult` |
| `OutputGuardrail` | Protocol | `name`; `async check(output_text) -> GuardrailResult` |

### Submodules
| Module | Symbols |
|---|---|
| `agentkit.guardrails._registry` | `resolve_guardrails(names) -> [...]` |
| `agentkit.guardrails._runner` | `execute_input_guardrails(...)`, `execute_output_guardrails(...)` — **fail-open** |
| `agentkit.guardrails.input/` | `content_safety`, `input_length`, `prompt_shield` |
| `agentkit.guardrails.output/` | `pii_filter` |

## Dependencies
- Within agentkit: `agentkit.tokens` (length check), `agentkit.observability` (metrics).
- pip extra: none — `pydantic`, `httpx`, `azure.identity` are all base deps. Content Safety uses raw `httpx` + a token (no content-safety SDK).

## Injection seams
- **Guardrail selection** — the consumer resolves names from its config (GridIQ: `control/agent_config.yaml`) via `resolve_guardrails` and injects the resulting chains at the chat-router / streaming-service boundary.

## Extend recipe
- **Add a guardrail** → implement the `InputGuardrail`/`OutputGuardrail` shape (a class with `name` + async `check`) under `input/` or `output/`; register it in `_registry`. Reference it by name in consumer config.

## Gotchas
- **Fail-open by contract**: a guardrail must not raise on transient failure — return `PASS` with `reason="error: ..."`. The runner swallows and continues so a safety-check outage never breaks chat.
- Output `BLOCK` is **advisory** post-stream (content already sent) — logged for audit, not retroactively enforced.

## Zero-domain assertion
Imports zero consumer package and no SDK beyond base deps. Genuinely generic AI-safety primitives, not domain content (lifted from `ops.guardrails`; domain phrasing removed from docstrings).
