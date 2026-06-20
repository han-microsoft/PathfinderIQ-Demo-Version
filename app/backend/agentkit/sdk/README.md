# agentkit.sdk

The concrete agent-framework SDK binding — the **only** place an external agent SDK is imported. Isolate-SDK-quirks doctrine.

## Purpose
- Wrap exactly one external *agent framework* SDK so `agentkit.core` stays SDK-free. Today the only binding is the Microsoft Agent Framework (MAF) seam in `maf_client`. Swapping SDKs = a sibling module here, never a core edit.

## Public API
`from agentkit.sdk.maf_client import ...`

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `maf_available` | fn | `() -> bool` | True if `agent_framework` is importable |
| `build_compaction_strategy` | fn | `(token_budget: int, tokenizer) -> Any \| None` | MAF compaction strategy; `None` when SDK absent |
| `build_tracing_middleware` | fn | `() -> list` | MAF tracing middleware; `[]` when SDK absent |

`from agentkit.sdk import azure_openai_agent_client` (batteries-included factory, `azure_client`)

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `azure_openai_agent_client` | fn | `(*, endpoint, model_deployment, credential=None, api_version=None) -> Callable[[], client]` | One-line, ready-to-inject zero-arg Azure `AgentClient` factory. Lazily imports `agent_framework.azure` (`[maf]`) + `azure.identity` (`[azure]`) **inside** the returned factory; defaults to a single cached `DefaultAzureCredential()`. ImportError names `agentkit[maf,azure]` when the SDK is absent. Generalises GridIQ's `agent_client_factories.py`. |

> `maf_client` is the agent-runtime **SDK client** seam. It is distinct from `agentkit.tools.adapters` (the datasource *tool* adaptors). "SDK binding" ≠ "datasource adaptor" — the naming split is deliberate (renamed from `agentkit.adapters` in Inc11b).

## Dependencies
- Within agentkit: imported lazily by `agentkit.core.compaction` and `agentkit.core.middleware`.
- pip extra: **`[maf]`** (`agent-framework`). See note below.

## Injection seams
This module *is* the seam. `agentkit.core.builder` accepts any object satisfying `agentkit.core.AgentClient` (`as_agent(...)`); the consumer's composition root constructs the concrete MAF-backed client and injects it. The kit's own `AgentApp` quickstart injects a stub `AgentClient` instead (no SDK).

## Extend recipe
- **Bind a different LLM SDK** → add `agentkit/sdk/<newsdk>_client.py` exposing the same trio (`*_available`, `build_compaction_strategy`, `build_tracing_middleware`) + an `AgentClient` factory. Inject its factory through `AgentRegistry.configure`. No change to `core`.

## Gotchas
- Imports are lazy at the call boundary: importing this package does **not** import the SDK. The base wheel boots without `agent_framework`; the strategies/middleware degrade to `None`/`[]`.
- **Extra:** `pyproject.toml` declares `[maf]` (`agent-framework`, `agent-framework-core`). These are also hard base dependencies of GridIQ today; a standalone consumer installs `agentkit[maf]`.

## Zero-domain assertion
Imports no consumer package. The only non-stdlib import is the SDK itself (lazy).
