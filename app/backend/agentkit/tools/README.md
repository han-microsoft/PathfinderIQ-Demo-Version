# agentkit.tools

Generic, domain-blind tool-construction machinery: the SDK-free `@tool` decorator a tool author uses (Inc13a) + the `adapters/` datasource layer (the reusable READ-tool transport spine, Inc10).

## Purpose
- Give a tool author ONE import — `from agentkit.tools import tool` — instead of leaking the concrete SDK (`from agent_framework import tool`). The decorator only stamps agent-callable metadata; the SDK binding happens later, so the same tool script runs against MAF, the echo/mock client, or a future SDK with no edit.
- Stop every datasource tool re-implementing the same ~80–90% boilerplate: *resolve config → cache/construct client → validate (read-only guard) → acquire resilience gate → execute (`asyncio.to_thread`) → shape → cap → release gate + record breaker → on error return an envelope.* That spine lives once per backend in `agentkit.tools.adapters`.

## The `tool` decorator (Inc13a)
`from agentkit.tools import tool`

| Symbol | Kind | Signature | Behaviour |
|---|---|---|---|
| `tool` | decorator factory | `tool(*, approval_mode="never_require", description=None)` | Stamps `fn.__agentkit_tool__ = {"approval_mode", "description" (or `fn.__doc__`)}` and returns `fn` **UNWRAPPED** — same object, signature, behaviour. |

- **Zero SDK at load.** This module imports NO `agent_framework`; `agentkit.tools` stays importable in the base wheel (the `hello_agent` echo example imports it clean).
- **The SDK binding is deferred** to `agentkit.sdk.maf_client.bind_tools(tools, client)`, called by `agentkit.core.builder.build_agent` just before `client.as_agent(...)`. For a MAF client each marked callable is wrapped with the real `agent_framework.tool(approval_mode=...)`; for a non-MAF client (echo/mock) the marker is ignored and the raw callable is used.
- **Decorator order.** Place `@tool` OUTERMOST exactly where the SDK `@tool` sat (e.g. over `@traced_tool(...)`), so the SDK binding wraps the fully-decorated callable at build time — byte-identical to the prior import-time wrapping.

```python
from agentkit.tools import tool
from agentkit.observability import traced_tool

@tool(approval_mode="never_require")
@traced_tool("my_tool", backend="my_backend")
async def my_tool(arg: str) -> str:
    """What the agent sees as the tool description (defaults to this docstring)."""
    ...
```

## Public API — adapters
`from agentkit.tools.adapters import ...`

| Symbol | Kind | Backend (extra) | Returns |
|---|---|---|---|
| `KqlToolAdapter` | class | Fabric Eventhouse / Kusto (`[kusto]`) | `str` — `{"columns","rows"}` |
| `KqlTarget` | dataclass | — | endpoint+db target for the resolver |
| `shape_kusto_response` | fn | — | raw Kusto response → `{"columns","rows"}` |
| `GremlinToolAdapter` | class | Cosmos Gremlin (`[gremlin]`) | `str` — JSON list |
| `GremlinTarget` | dataclass | — | gremlin endpoint target |
| `SearchToolAdapter` | class | Azure AI Search (`[search]`) | `str` — `{"results","count"}` |
| `GraphToolAdapter` | class | Fabric GQL over HTTP (`httpx`) | **`dict`** — `{"columns","data"}` (the projection seam) |
| `GraphRetryBudget` | dataclass | — | GQL retry budget config |
| `HttpToolAdapter` | class | bearer-token JSON service (`httpx`) | `str` — consumer-projected |
| `DataSourceAdapter` / `ResilienceGate` | Protocol | — | the adaptor + gate seams |

> `GremlinToolAdapter`/`GremlinTarget`/`SearchToolAdapter` are lazily imported via PEP-562 `__getattr__` so a bare `from agentkit.tools.adapters import KqlToolAdapter` never imports the gremlin/search SDKs.

## Dependencies
- Within agentkit: `contracts` (envelope), `config`, `resilience`, `cloud`.
- pip extras (**real, declared**): `[kusto]`, `[gremlin]`, `[search]`, `[adapters]` (all three). `graph`/`http` use `httpx` (base).

## Injection seams (the data-boundary law)
1. **Config/credential via an injected resolver** — an adaptor never reads a consumer's request scope. Endpoint / database / index / credential / gate arrive as constructor callables: `resolve_target` / `resolve_endpoint` (zero-arg; the consumer closes over its own scope), `credential_provider`, `token_provider`, `gate_provider`.
2. **Projection stays consumer-side** — the adaptor shapes a *generic* envelope and never embeds a domain projection. The consumer applies its categorical projection via an injected `project` hook (KQL/Gremlin), a `project_doc` per-hit hook (Search), or by projecting the adaptor's raw `dict` return (Graph). The `dict` return *is* the seam.
3. **Consumer guards** — `validate_fn` (read-only guard), `transform_query` (e.g. limit injection), error-detail callbacks (`sanitize_error`, `degraded_detail`, `on_*_error`) are all injected so byte-exact error envelopes stay consumer-defined.

## Extend recipe — a new datasource tool (~30 lines vs ~190)
```python
from agentkit.tools.adapters import KqlToolAdapter, KqlTarget

_adapter = KqlToolAdapter(
    resolve_target=lambda: KqlTarget(my_uri(), my_db()),  # resolver seam
    credential_provider=my_credential,                    # injected cred
    gate_provider=lambda: my_throttle_gate(),             # injected gate
    validate_fn=my_read_only_guard,                       # consumer guard
    transform_query=my_limit_injector,                    # consumer query text
)

async def execute(query: str) -> str:
    return await _adapter.execute(query, project=my_projection)  # consumer projection
```
- **A brand-new backend** → add `agentkit/tools/adapters/<x>_adapter.py` owning the spine; expose it (lazy if its SDK is heavy) from the package `__init__`.

## Gotchas
- The adaptor **exposes** circuit-open state (never hides it) so a consumer tool can degrade.
- Whole-file LOC of a converted tool stays ~flat — the win is the ~130–230 line transport spine moving **once** into the adaptor; net-new tools are tiny.
- Test monkeypatches target the adaptor's `_get_client` (e.g. `tools.search._aisearch.client._search_read_adapter._get_client`), not the old per-tool client builders.

## Zero-domain assertion
Imports ZERO consumer package (grep-clean). No projection, no domain vocabulary baked in — that would drag the consumer's domain into agentkit and break the data boundary.
