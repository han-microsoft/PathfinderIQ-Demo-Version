# agentkit.persistence

Session-store layer (F3): a domain-blind `SessionStore` protocol, a pure in-memory store, and an injected-client Cosmos base. The `[cosmos]` layer for the durable backend.

## Purpose
- Type the agent runtime against a domain-blind session store (CRUD + per-agent threads + health/close), with a zero-infra in-memory default and a swappable durable backend.

## Public API
`from agentkit.persistence import ...`

| Symbol | Kind | Does |
|---|---|---|
| `SessionStore` | Protocol | CRUD + threads + `is_healthy`/`close`, typed on `SessionBase`/`SessionSummaryBase` — **no** domain hooks |
| `InMemorySessionStore` | class | pure stdlib store; the quickstart default + Phase-1 fallback; `default_agent_id` injected |

`SessionStore` methods: `create`, `get`, `list_all`, `update`, `delete`, `append_message`, `update_message`, `get_thread`, `create_thread`, `get_thread_messages`, `is_healthy`, `close`.

### `agentkit.persistence.cosmos` (import explicitly — NOT re-exported)
| Symbol | Kind | Does |
|---|---|---|
| `CosmosContainerStore` | class | Cosmos base; **client + container injected** (zero azure import in the base), B-COSMOS-ASYNCIO baked in |
| `CosmosStoreUnavailable` | exc | raised when the store cannot serve |

## Dependencies
- Within agentkit: `contracts` (`SessionBase`/`SessionSummaryBase`/`AgentThread`/`Message`). `protocol` + `memory` pull **zero** azure.
- pip extra: **`[cosmos]`** for `cosmos.py` (`azure-cosmos`). Declared in `pyproject.toml`; also a hard base dep of GridIQ today. The in-memory store needs no extra.

## Injection seams
- **Cosmos client/credential** — injected: a consumer subclass builds `DefaultAzureCredential` + `CosmosClient` and forwards them via `super().__init__(client=..., container=...)`. The agentkit base duck-types `container.query_items` / `client.close`.
- **Domain session hooks** — the generic protocol deliberately omits `set_scenario`/`load_templates`/`iter_owned_sessions`; consumers add them in their own `SessionStore(_GenericSessionStore, Protocol)` and store subclasses.

## Extend recipe
- **Plug a durable store** → subclass `CosmosContainerStore` (or implement `SessionStore` for another backend); build the client behind your credential seam; pass it to `AgentApp(store=...)`. The in-memory default needs no infra.
- **Add domain session state** → subclass `SessionBase` (in `contracts`) for the fields and extend the protocol/store in your consumer; `agentkit` stays blind.

## Gotchas
- **`cosmos` is intentionally not re-exported** from the package `__init__` — eagerly importing it would drag azure onto the base import path. `from agentkit.persistence.cosmos import CosmosContainerStore` explicitly.
- **B-COSMOS-ASYNCIO**: `import asyncio` at module top is load-bearing for `is_healthy`'s `asyncio.timeout`; the `except Exception` swallow must never mask a `NameError`. It now lives in one base file so the gotcha can't recur per subclass.
- Field-diff `SessionBase` subclasses old-vs-new before shipping (inc5 dropped-field class).

## Zero-domain assertion
`protocol` and `memory` import zero azure and zero consumer package (grep-clean). The Cosmos base imports no azure either — the client is injected.
