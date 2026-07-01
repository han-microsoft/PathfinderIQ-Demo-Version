# agentkit.observability

Domain-blind OpenTelemetry + structured-logging plumbing + the `llmops/` per-invocation trace subpackage. Real pip extras: `[otel]`, `[azure-monitor]`, `[otlp]`, `[llmops]`.

## Purpose
- Boot OTel tracer/meter providers, emit structured JSON logs, carry a correlation-id through requests, and decorate every tool with a span+log+metric (`@traced_tool`). Degrades to noop when OTel is absent.
- `llmops/` records per-LLM-invocation traces, estimates cost, and exports them via pluggable exporters (jsonl).

## Public API
`from agentkit.observability import ...`

| Symbol | Kind | Does |
|---|---|---|
| `configure` | fn | composition-root bootstrap (call once) |
| `shutdown_observability` | fn | flush/close exporters on shutdown |
| `set_service_name` | fn | inject the OTel service name (domain label) |
| `traced_tool` | decorator | span + structured log + metric per tool call; reraises; redacts |
| `get_tracer` / `get_meter` | fn | manual spans / metrics |
| `get_tool_call_counter` / `get_tool_duration_histogram` / `get_tool_error_counter` | fn | the tool metric instruments |
| `set_metric_namespace` | fn | inject the meter namespace (domain label) |

### `agentkit.observability.llmops`
`configure_llmops`, `estimate_cost`, the per-invocation trace records + async export queue + exporters (jsonl). `from agentkit.observability.llmops import configure_llmops, estimate_cost`.

## Dependencies
- Within agentkit: `config`. Plus `fastapi` (base dep, for the ASGI middleware) and the optional OTel / json-logger SDKs.
- pip extras (**real, declared**): `[otel]` (OTel SDK + auto-instrumentation + json-logger), `[azure-monitor]` (App Insights exporter), `[otlp]` (OTLP gRPC exporter), `[llmops]` (marker — pydantic is base).

## Injection seams
- **Service name / metric namespace** — `set_service_name(...)` / `set_metric_namespace(...)` injected by the composition root (the only domain labels).
- **LLMOps exporter** — selected by `get_settings().llmops_backend` (env alias `LLMOPS_BACKEND`).

## Extend recipe
- **Trace a tool** → `@traced_tool` on the tool function (it is in the hot path — keep it cheap).
- **Add an LLMOps exporter** → implement the exporter protocol in `llmops/_exporters/` and wire it by `LLMOPS_BACKEND` name.
- **Export to a new OTel target** → set `OTEL_EXPORT_TARGET` + the matching extra (`azure`/`otlp`); no code change.

## Gotchas
- **`llmops_backend` is alias-only**: declared with `validation_alias=AliasChoices("LLMOPS_BACKEND")` and no `populate_by_name`. Set it via `monkeypatch.setenv("LLMOPS_BACKEND", "jsonl")` — a kwarg is silently ignored.
- **Settings test pattern**: save/restore `agentkit.config.settings._active_settings` (raw global) around `configure_settings(...)`; never call `get_settings()` to snapshot (it lazily builds a bare settings object that ValidationErrors on required azure fields).
- Noop-safe: without the `[otel]` SDK, tracer/meter fall back to noop and JSON logging degrades to a plain formatter — boot still succeeds.

## Zero-domain assertion
Imports zero consumer package (grep-clean). Domain labels (service name, meter namespace) are injected, never hard-coded.
