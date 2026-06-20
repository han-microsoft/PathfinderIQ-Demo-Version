# agentkit

A **domain-blind, reusable kernel for building streaming, tool-calling agent applications.** Extracted from GridIQ; imports **zero** consumer/domain packages. GridIQ is its first consumer — but nothing in here knows what GridIQ is.

What you get: declarative (YAML) agent definitions, a fail-closed tool runtime, an SDK-agnostic LLM seam, an SSE streaming spine with a contract probe, a session store (in-memory + injected-Cosmos), resilience primitives, observability, AI-safety guardrails, datasource adaptors, and a few-lines `AgentApp` facade.

- Internal distribution only — never public PyPI.
- Lineage: [../genericize/TIER1_EXTRACTION_PLAN.md](../genericize/TIER1_EXTRACTION_PLAN.md) (canonical layout + DAG) and [../genericize/GENERICIZATION_AUDIT.md](../genericize/GENERICIZATION_AUDIT.md).

---

## What agentkit is

A kernel — the orchestration, contracts, transport, and persistence interfaces an agent app needs — with every domain-specific concern pushed out through an injection seam. You bring the LLM SDK client, the tools, the domain projection, the durable store, and the request scope; agentkit wires them into a streaming, tool-calling agent with a FastAPI/SSE surface.

It contains **no** domain knowledge: no station codes, no KQL/Gremlin/Fabric specifics, no situation detector, no CIM vocabulary. Domain lives entirely in the consumer.

---

## The hard rules (invariants every extender MUST keep)

1. **agentkit imports zero consumer-domain packages.** The dependency arrow points one way: `consumer → agentkit`. Never `foundation`/`tools`/`agent`/`hosting`/`app`/`ops` (GridIQ's packages) inside agentkit.
2. **Inward-only dependency DAG.** A layer imports only layers to its left:

   ```mermaid
   graph LR
     contracts --> config --> resilience
     config --> validation
     config --> cloud
     config --> tokens
     contracts --> core
     config --> core
     tokens --> core
     core --> sdk
     contracts --> hosting
     config --> hosting
     contracts --> persistence
     config --> observability
     tokens --> guardrails
     observability --> guardrails
     contracts --> tools
     config --> tools
     resilience --> tools
     cloud --> tools
     core --> app
     hosting --> app
     persistence --> app
   ```

   `contracts` is the innermost ring (stdlib + pydantic). `app` is the capstone that wires everything. `hosting` is transport-only; `app` is the only composition root.
3. **The data-boundary law.** No domain vocabulary, no secrets, and no domain projection inside agentkit. Datasource adaptors return *generic* envelopes; the consumer applies its categorical projection. Examples in these docs use a neutral echo/calculator domain only.
4. **Every injected seam is a Protocol/callable the consumer supplies.** `AgentClient`, datasource resolver + projection hook, `SessionStore`, `request_scope_builder`, domain-event registration, tool-allowlist prefixes. agentkit never reaches into consumer state — it calls the callable you injected.
5. **pip extras gate heavy deps.** The base import path is lean (stdlib + pydantic/pydantic-settings + pyyaml + httpx). Backend SDKs (Kusto, Gremlin, Search), the MAF/Azure clients, FastAPI transport, and OTel exporters are lazy, behind extras. Standalone manifest: [pyproject.toml](pyproject.toml).

---

## Quickstart

New here? Start with the **[getting-started ladder](GETTING_STARTED.md)** — zero → a real Azure-backed, tool-calling agent in seven copy-paste rungs (install → echo agent → real model → `create_app` → custom tool → settings → serve).

The canonical starting point is [`examples/hello_agent/`](examples/hello_agent/) — a working streaming agent in a few lines using ONLY agentkit (a stub client, the in-memory store, no Azure, no consumer import).

```python
# examples/hello_agent/app.py  — the whole wiring
from agentkit.app import AgentApp
from agentkit.config import BaseAgentSettings
from agentkit.examples.hello_agent.stub_client import EchoClientFactory

def build_app() -> AgentApp:
    return AgentApp(
        BaseAgentSettings(llm_provider="agent", llm_model="echo-1", auth_enabled=False),
        config=_HERE / "agent_config.yaml",
        agent_client=EchoClientFactory(),                       # the only SDK seam
        allowed_tool_prefixes=("agentkit.examples.hello_agent.",),
        default_agent_id="hello",
    )
```

```yaml
# agent_config.yaml — the entire declarative surface
agents:
  default: hello
  hello:
    name: HelloAgent
    description: "A neutral echo agent that proves the agentkit wiring end to end."
    instructions: [hello.md]
    tools:
      - agentkit.examples.hello_agent.echo_tool:echo
```

```python
# echo_tool.py — a tool is just a callable
def echo(text: str) -> str:
    return f"echo: {text}"
```

Run it headless (prints `token`/`done` events):

```bash
python3 -m agentkit.examples.hello_agent.app
```

**Echo → a real LLM:** replace `EchoClientFactory()` with a factory backed by `agentkit.sdk.maf_client` (the Microsoft Agent Framework seam). Change nothing else. **Add a tool:** one line under `tools:` + widen `allowed_tool_prefixes`. **Serve over HTTP:** `build_app().serve()` (the `[fastapi]` surface).

---

## Package map

Each row links to that subpackage's README. "Depends-on" lists agentkit-internal deps (per the DAG).

| Subpackage | Purpose | Key public symbols | pip extra | Depends-on |
|---|---|---|---|---|
| [`contracts/`](contracts/README.md) | wire/boundary types + error taxonomy + tool envelope | `StreamEvent`, `StreamEventType`, `Message`, `ToolCall`, `SessionBase`, `error_envelope`, `ErrorCode`, `classify_error` | — (pydantic, base) | — |
| [`config/`](config/README.md) | settings base + request scope | `BaseAgentSettings`, `BaseAgentSettings.from_env`, `get_settings`, `configure_settings`, `RequestScope` | — (base) | — |
| [`resilience/`](resilience/README.md) | circuit breaker + retry + fallback queue | `CircuitBreaker`, `registry`, `should_retry`, `get_model_fallback_queue` | — (base) | config |
| [`validation/`](validation/README.md) | input shape-gates + tool-call ledger | `require_station`, `validate_session_id`, `record_tool_call_once` | — (base) | — |
| [`cloud/`](cloud/README.md) | Azure credential factory | `get_azure_credential` | `[azure]`¹ | — |
| [`tokens/`](tokens/README.md) | tiktoken counter | `count_tokens` | `[tokens]`¹ | config |
| [`core/`](core/README.md) | agent runtime (K1–K10) | `AgentRegistry`, `build_agent`, `resolve_tools`, `AgentClient`, `set_default_allowed_prefixes` | — (base) | contracts, config, tokens, sdk |
| [`sdk/`](sdk/README.md) | the only SDK binding (MAF) | `maf_available`, `azure_openai_agent_client`, `build_compaction_strategy`, `build_tracing_middleware` | `[maf]`¹ | — |
| [`hosting/`](hosting/README.md) | SSE transport spine + runtime + devauth | `format_sse`, `map_update_to_events`, `register_domain_events`, `check_event_sequence`, `BoundedEventChannel`, `install_signed_request_auth` | `[fastapi]`¹ | contracts, config |
| [`persistence/`](persistence/README.md) | session store | `SessionStore`, `InMemorySessionStore`, `CosmosContainerStore` | `[cosmos]`¹ | contracts |
| [`observability/`](observability/README.md) | OTel + structured logs + llmops | `traced_tool`, `configure`, `get_tracer`, `get_meter` | `[otel]`,`[azure-monitor]`,`[otlp]`,`[llmops]` | config |
| [`guardrails/`](guardrails/README.md) | AI-safety chain | `GuardrailVerdict`, `InputGuardrail`, `OutputGuardrail`, `resolve_guardrails` | — (base) | tokens, observability |
| [`tools/`](tools/README.md) | `@tool` decorator + datasource adaptors | `tool`, `KqlToolAdapter`, `GremlinToolAdapter`, `SearchToolAdapter`, `GraphToolAdapter`, `HttpToolAdapter` | `[kusto]`,`[gremlin]`,`[search]`,`[adapters]` | contracts, config, resilience, cloud |
| [`dev_tools/`](dev_tools/README.md) | headless dev/CI CLIs | `dev_sign.main`, `sse_contract_probe.main` | — | hosting |
| [`app/`](app/README.md) | `AgentApp` facade (capstone) | `AgentApp` (`.chat`/`.router`/`.serve`), `create_app` | `[fastapi]`¹ | core, hosting, persistence |
| [`examples/hello_agent/`](examples/hello_agent/README.md) | zero-infra quickstart | `build_app` | — | app |

¹ **Declared as an opt-in extra in `pyproject.toml`; also a hard base dep of GridIQ (it uses every path), so present in-tree today.** See [pip extras](#pip-extras).

---

## The injection seams

Everything domain-specific plugs in here. agentkit calls the callable/object you supply; it never reaches into your state.

| Seam | Where | Signature | What the consumer supplies |
|---|---|---|---|
| **AgentClient** | `core.AgentClient` / `AgentRegistry.configure` / `AgentApp(agent_client=)` | object with `as_agent(*, name, tools, ...) -> agent` (a `() -> client` factory) | the concrete LLM SDK client (MAF via `agentkit.sdk`, or a stub). The only SDK seam. |
| **Datasource resolver** | adaptor ctor (`resolve_target`/`resolve_endpoint`, `credential_provider`, `token_provider`, `gate_provider`) | zero-arg callables | per-request endpoint/db/index/credential/gate, closing over the consumer's own scope |
| **Projection hook** | adaptor `execute(..., project=)` / per-hit `project_doc` / raw `dict` return | `(raw) -> domain shape` | the categorical/domain projection of a generic result (stays consumer-side) |
| **SessionStore** | `persistence.SessionStore` / `AgentApp(store=)` | the CRUD+threads Protocol | a durable backend (or use the in-memory default); Cosmos client is injected too |
| **request_scope_builder** | `AgentApp(request_scope_builder=)` (K9) | `() -> RequestScope` (fills opaque `services`/`bindings`) | per-request domain config; agentkit only carries the opaque bags |
| **Domain events** | `hosting.register_domain_events` / `AgentApp(domain_events=)` | `(names: Iterable[str]) -> None` | raw-string SSE event names on top of the generic vocabulary |
| **Tool allowlist** | `core.set_default_allowed_prefixes` / `AgentApp(allowed_tool_prefixes=)` | `tuple[str, ...]` | the importable-module prefixes (`()` = fail-closed, forbids all) |
| **Guardrails** | `guardrails.resolve_guardrails` | `(names) -> [InputGuardrail/OutputGuardrail]` | which safety checks to run, from consumer config |

---

## How to EXTEND

Concrete recipes — each is *minimal steps + which file/seam*.

- **Add a tool** → write a callable, decorate it with `@tool` from `agentkit.tools` (SDK-free; stamps the agent-callable marker), and declare it as `module:function` under an agent's `tools:` in the YAML (must match an `allowed_tool_prefixes` entry). The SDK binding is applied at build time by `agentkit.sdk.maf_client.bind_tools`. For a *datasource* tool, also instantiate the matching adaptor in `agentkit.tools.adapters`, supply the resolver + projection hook. No core/router edit.
- **Add an agent** → one block under `agents:` in `agent_config.yaml` (`name`, `description`, `instructions: [x.md]`, `tools: [...]`). Zero code.
- **Add a new datasource adaptor** → new `agentkit/tools/adapters/<x>_adapter.py` owning the transport spine; expose it (lazy if its SDK is heavy) from the package `__init__`. Keep projection consumer-side.
- **Swap the LLM SDK** → write a sibling `agentkit/sdk/<newsdk>_client.py` exposing an `AgentClient` factory; inject its factory via `AgentRegistry.configure`. `core` is untouched.
- **Add a guardrail** → implement the `InputGuardrail`/`OutputGuardrail` shape under `guardrails/input|output/`; register in `_registry`; reference by name in consumer config. Fail-open.
- **Plug a durable session store** → subclass `CosmosContainerStore` (inject the client behind your credential seam) or implement `SessionStore` for another backend; pass to `AgentApp(store=...)`.
- **Add a domain SSE event** → `register_domain_events(("my_event",))` in the consumer (never in the agentkit enum); the contract probe then accepts it.

---

## pip extras

The base install (`agentkit` with no extras) is lean: **pydantic + pydantic-settings + pyyaml + httpx** only (the four libs the kernel imports unconditionally at module load). Every heavy SDK is lazy and gated behind an extra.

### Standalone install

agentkit ships its own distribution manifest at [`pyproject.toml`](pyproject.toml) (inside this package dir). Build/install it on its own — independent of GridIQ:

```bash
# build the lean wheel
python3 -m build --wheel agentkit/ --outdir dist/

# install with only the extras you need
pip install "agentkit[maf,fastapi]"        # MAF client + SSE transport
pip install "agentkit[adapters,cosmos]"    # datasource adaptors + Cosmos store
pip install "agentkit[all]"                # everything except [dev]
```

A bare `pip install agentkit` pulls only pydantic/pydantic-settings/pyyaml/httpx (+ transitive) — no agent-framework, no azure-*, no gremlin/kusto. Proven by a fresh-venv install of the built wheel running the [`examples/hello_agent`](examples/hello_agent/) echo stream out-of-tree.

> The two manifests share version pins verbatim and must not drift: [`pyproject.toml`](pyproject.toml) is agentkit's standalone manifest; [`../pyproject.toml`](../pyproject.toml) remains GridIQ's deploy manifest (the container image is built from the root only — this sibling file is inert to that build).

**Extras (declared identically in both manifests):**

| Extra | Unlocks |
|---|---|
| `[kusto]` | `azure-kusto-data` — `KqlToolAdapter` |
| `[gremlin]` | `gremlinpython` — `GremlinToolAdapter` |
| `[search]` | `azure-search-documents` — `SearchToolAdapter` |
| `[adapters]` | all three datasource SDKs at once |
| `[otel]` | OTel SDK + auto-instrumentation + json-logger (spans/metrics export) |
| `[azure-monitor]` | App Insights exporter (`OTEL_EXPORT_TARGET=azure`) |
| `[otlp]` | OTLP gRPC exporter |
| `[azure]` | `azure-identity` — `agentkit.cloud` credential factory |
| `[tokens]` | `tiktoken` — `agentkit.tokens` counter |
| `[cosmos]` | `azure-cosmos` — `agentkit.persistence` Cosmos store base |
| `[fastapi]` | `fastapi`, `uvicorn[standard]`, `sse-starlette` — `agentkit.hosting`/`AgentApp` transport |
| `[maf]` | `agent-framework`(+`-core`) — `agentkit.sdk` Microsoft Agent Framework binding |
| `[dev]` | ruff, pytest, pytest-asyncio/cov/timeout, httpx |

**On the `¹` extras (`[azure]`,`[tokens]`,`[cosmos]`,`[fastapi]`,`[maf]`):** these are declared in BOTH manifests. In GridIQ's root manifest they are also hard base deps (GridIQ exercises every path), so the libs are present in-tree there. In agentkit's own [`pyproject.toml`](pyproject.toml) they are extras ONLY — a standalone `pip install agentkit` does NOT pull them; the kernel imports each lazily at its seam, so a standalone consumer installs only the extras it uses. (This is the standalone-wheel work that earlier docs deferred — now done.)

graph/http adaptors use `httpx` only (a base transport dep — no extra).

---

## Testing + dev tools

- **Signed requests** — `python3 -m agentkit.dev_tools.dev_sign {init|pubkey|sign|request}` manages a local Ed25519 keypair (`~/.gridiq/dev_signing_key`, `0600`) and signs/executes requests against the devauth side-channel. Only the public key is pushed to the app (`DEV_PUBLIC_KEY_ED25519`); re-push it after any full deploy that strips it.
- **Wire contract** — `python3 -m agentkit.dev_tools.sse_contract_probe --base-url <url>` drives one chat round-trip and asserts the SSE event-sequence contract (one terminal frame, matched tool-call ids, byte cap, known vocabulary). Exit `0`/`1`/`2`.
- **Settings-test gotcha** — a `validation_alias`-without-`populate_by_name` field (e.g. `llmops_backend` ← `LLMOPS_BACKEND`) can be set **only** via the env-var alias (`monkeypatch.setenv`), never a kwarg. And in isolated tests save/restore the raw module global `agentkit.config.settings._active_settings` around `configure_settings(...)` — never call `get_settings()` to snapshot it (it lazily builds a bare settings object that ValidationErrors on required fields).
- agentkit-facing unit tests live under [../tests/unit/](../tests/unit) (e.g. `test_agentkit_adapters.py`, `test_agentkit_hosting_sse.py`, `test_agentkit_observability.py`, `test_agentkit_guardrails.py`, `test_hello_agent_example.py`, `test_tool_resolver_fail_loud.py`).

---

## Provenance

agentkit was extracted from GridIQ across a sequence of increments (inc1–inc13b), each a deploy + 25/25 live regression cycle. The canonical package layout and the inward-only dependency DAG are specified in [../genericize/TIER1_EXTRACTION_PLAN.md](../genericize/TIER1_EXTRACTION_PLAN.md) §4/§4.1; the full extraction history, design seams, landmines, and the data-boundary law live in the repo memory note `/memories/repo/agentkit-extraction.md`. Complete: Tier-1 (inc1–9) + datasource adaptors (inc10) + observability/guardrails (inc11) + streaming/runtime/dev-tools polish (inc12) + the `@tool` template (inc13a) + the chat-runtime lift / agent-surface collapse (inc13b — the generic chat run loop now lives in `agentkit.hosting.run_engine`/`run_loop`/`completion` + `agentkit.core.agent_builder`; GridIQ's `agent_framework.py` is a ~500 LOC `LLMService` facade injecting only the SDK seam + domain revival wording). The `devauth` `User`-protocol seam (inc14) is the only remaining deferred (auth-coupled) lift candidate — not yet shipped.

### Layout

```
agentkit/
  contracts/           # wire/error/session types + tool error envelope   (innermost)
  config/              # BaseAgentSettings + request scope + get/configure_settings
  resilience/          # circuit breaker + retry + model-fallback queue
  validation/          # input sanitisers + tool-call ledger
  cloud/               # Azure credential factory
  tokens/              # tiktoken counter
  core/                # agent runtime (config_loader, registry, resolver, builder, providers, …)
  sdk/maf_client.py    # the ONLY file importing agent_framework (lazy)
  hosting/             # SSE transport spine (sse/ + runtime/) + abort registry + probe + devauth/ (Ed25519 signed-request)
  persistence/         # session store Protocol + in-mem + Cosmos base
  observability/       # OTel tracing/metrics/logging/middleware + llmops/
  guardrails/          # AI-safety chain (content-safety/prompt-shield/PII/length)
  tools/adapters/      # datasource adaptors (KQL/Gremlin/Search/GQL/HTTP)
  dev_tools/           # dev_sign + sse_contract_probe CLIs
  app/                 # AgentApp facade (capstone)
  examples/hello_agent/    # zero-infra quickstart
```
