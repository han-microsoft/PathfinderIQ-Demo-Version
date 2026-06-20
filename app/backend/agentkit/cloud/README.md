# agentkit.cloud

Generic 3-tier Azure credential factory.

## Purpose
- One credential entry point exposing a cached `DefaultAzureCredential`-style credential, usable identically on a developer machine (CLI login) and in cloud (workload identity). Managed Identity by default — no keys, no connection strings.

## Public API
`from agentkit.cloud import get_azure_credential`

| Symbol | Kind | Signature | Does |
|---|---|---|---|
| `get_azure_credential` | fn | `() -> TokenCredential` | returns a cached Azure credential (3-tier: managed identity → CLI → interactive fallback per impl). `azure.identity` imported lazily inside the call. |

## Dependencies
- Within agentkit: none.
- pip extra: **`[azure]`** (`azure-identity`). See note below.

## Injection seams
None directly. Consumers pass the returned credential into adaptors via a `credential_provider` callable (see `agentkit.tools.adapters`) or into the Cosmos store base.

## Extend recipe
- **Use the credential for a new SDK client** → `cred = get_azure_credential(); client = SomeAzureClient(endpoint, credential=cred)`. Build the client behind a resolver/provider seam so agentkit stays out of consumer scope.

## Gotchas
- The factory is import-light: `azure.identity` is imported lazily inside the call, so importing `agentkit.cloud` never requires the SDK.
- **Extra:** `pyproject.toml` declares `[azure]` (`azure-identity`). It is also a hard base dependency of GridIQ today, so the dep is always present in-tree; a standalone consumer installs `agentkit[azure]` to get it.

## Zero-domain assertion
Imports no consumer package. No domain vocabulary or secrets.
