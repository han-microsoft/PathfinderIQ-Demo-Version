# Adapter Protocol — adding a new data source

Bolt a NEW managed-identity data source into VM-agent via the unified
[vmagent/tools/transport/adapter_base.py](../../vmagent/tools/transport/adapter_base.py)
`RestDataSourceAdapter`. The base owns **transport + error ONLY**; it is
ORTHOGONAL to `invoke_tool` (audit, profile, `ToolResult` envelope, `card_kind`
all stay in [registry.py](../../vmagent/tools/registry.py)). New source =
**subclass + declare class attrs + implement operations + wire one
`registry_defs` module**. Scope: `vm_agent/` only.

`fabric_ontology` is the reference impl. The 6 live adapters
(`fabric_ontology`, fabric 3-plane, cosmos, cosmos_gremlin, storage, search) are
the precedents cited below. `arm.py` is an unmigrated helper — NOT a registered
tool family; do not use it as a template.

## Architecture (read once)

- The base bundles the repeated MI-REST envelope: acquire a Bearer token for one
  `scope`, assemble auth + caller headers, build a `make_error_factory` closure,
  hand the request to the breaker-protected `mi_request`
  ([_http.py](../../vmagent/tools/transport/_http.py)).
- Layering: `adapter_base` (transport+error) ← the adapter module (operations) ←
  the thin `registry_defs/<x>.py` handlers (dict→dict) ← `registry.invoke_tool`
  (the ONLY owner of validation/audit/profile/envelope). Do NOT re-add audit or
  `card_kind` in the adapter — that double-emits.
- Constraints everywhere: **sync, managed-identity only** (no keys/SAS/conn
  strings/admin keys). The base reads no env — `get_token` is MI, env lives in
  [config.py](../../vmagent/config.py).

## Class-attr + knob contract

The actual base signature (read it, don't guess):

```python
class RestDataSourceAdapter:
    name: str = ""
    scope: str = ""
    error_cls: type[RuntimeError] = RuntimeError
    error_prefix: str = ""
    not_found: bool = False
    access_denied: bool = True
    timeout: int = 30
    truncate: int | None = None
```

| Attr | Set it when |
|---|---|
| `name` | label for the source family (e.g. `"cosmos"`). |
| `scope` | the single AAD token scope for the default plane (e.g. `https://cosmos.azure.com/`). |
| `error_cls` | a NEW `class <X>ToolError(RuntimeError)` you declare in the adapter module. |
| `error_prefix` | the code stem — every error string is `{error_prefix}_...`. |
| `not_found=True` | a `404` should map to `{prefix}_not_found` (else `404` stays `{prefix}_http_404`). |
| `access_denied=False` | **ONLY** if discovery wrappers STRING-MATCH `{prefix}_http_401/403`. Default `True` collapses 401/403 → `{prefix}_access_denied`. Flipping it silently rewrites those codes — see storage/search landmine below. |
| `timeout` / `truncate` | per-adapter request defaults (overridable per call). |

## Steps

1. **Declare the error class + subclass.** In `vmagent/tools/<x>.py`:
   `class <X>ToolError(RuntimeError): ...`, then
   `class _<X>Adapter(RestDataSourceAdapter):` with the class attrs above.
   Instantiate one module-level `_ADAPTER = _<X>Adapter()`.
2. **Implement operation methods** — sync, dict→dict, each calling
   `self.request(method, url, *, body=None, headers=None, scope=None, timeout=None, truncate=None)`.
   `request` returns the `mi_request` `(status, headers, body)` tuple unchanged;
   unpack it exactly as a hand-rolled call would. Caller `headers` win over the
   auth header on key collision.
3. **Override hooks only as needed** (the documented seams):
   - `_auth_header(scope=None)` — default `Bearer <get_token(scope or self.scope)>`.
     Override for **non-Bearer** auth. Cite cosmos: AAD-sig
     (`Authorization: type=aad&ver=1.0&sig=<url-encoded token>` + `x-ms-date` +
     `x-ms-version`), NOT Bearer.
   - **per-call `scope=`** on `request(...)` — for multi-cluster / multi-plane
     where ONE adapter spans scopes. Cite kusto (per-cluster scope) and storage
     (blob default scope + ARM via `scope=https://management.azure.com/`).
   - **multiple adapter instances** — one subclass per plane when scopes/prefixes
     differ structurally. Cite fabric: 3 plane adapters
     (control / kusto / onelake), control-plane token fallback via an
     `_auth_header` override.
   - `transport(...)` — override (NOT `request`) to swap `mi_request` for a sync
     SDK path while keeping the shared header + factory assembly. Rare.
   - `_factory()` — almost never overridden; tune via the class attrs instead.
4. **Non-REST backends are a SIDE-CHANNEL, not `request()`.** If a call is not
   MI-REST (an SDK), add a SEPARATE plain method — do NOT force it through
   `request()` (it would break the SDK's own auth + error code). Precedents:
   gremlin `run_gremlin` (gremlinpython over a `ThreadPoolExecutor`, flag-gated
   key auth) and search `_embed` (`AzureOpenAI` SDK, `cognitiveservices` token
   provider, emits `embedding_failed`). The adapter's ARM/REST plane still rides
   the base; only the SDK leg is the side-channel.
5. **Expose operations as tools** — add `vmagent/tools/registry_defs/<x>.py` with
   `def defs() -> dict[str, RegisteredTool]` returning bespoke-named entries.
   Handlers are sync dict→dict; `invoke_tool` owns profile/validation/audit/
   envelope — the handler just calls the adapter operation and returns its dict.

   ```python
   from vmagent.models.tools import RegisteredTool, ToolDefinition
   from vmagent.tools.registry_defs._common import _schema, _string_arg, text
   from vmagent.tools.<x> import some_operation

   def _some(args: dict) -> dict:
       return some_operation(name=_string_arg(args, "name"))

   def defs() -> dict[str, RegisteredTool]:
       return {
           "<x>.some": RegisteredTool(
               ToolDefinition(
                   name="<x>.some",
                   title="...",
                   description="...",
                   input_schema=_schema({"name": text}, ["name"]),
                   # risk="write" for mutations; omit for read
               ),
               _some,
           ),
       }
   ```

   Register the family in [registry.py](../../vmagent/tools/registry.py)'s
   `_defs()` aggregation (the choke point keeps `invoke_tool`/`list_tools`).
   Alternatively, a fully drop-in tool needs NO `registry.py` edit: ship a
   `toolsets/custom/<x>_tool.py` factory + one `toolsets/tool_manifest.json`
   line `{ "name": "<x>.some", "ref": "toolsets.custom.<x>_tool:register" }` —
   [loader.py](../../vmagent/tools/loader.py) imports the ref after `_defs()`
   and merges it into the same `_TOOLS` choke point (core wins on name collision).

6. **MANDATORY equivalence test.** Any new/changed adapter MUST snapshot-pin its
   error-code strings for `{None, 401, 403, 404, 500}` so drift fails loudly.
   This is the AUTODEV landmine rule — an `access_denied`/`not_found` flip or a
   prefix rename silently rewrites codes that discovery wrappers and
   `invoke_tool`'s `str(exc).split(":",1)[0]` extraction depend on. Precedents:
   [tests/test_http_error_factory_equivalence.py](../../tests/test_http_error_factory_equivalence.py),
   `tests/test_storage_adapter.py`, `tests/test_search_adapter.py` (assert NO
   `_access_denied` ever appears when `access_denied=False`; wrappers still match
   `_http_401/403/404`).

7. **Verify (no public-contract change).** Local gate:

   ```bash
   python3 -m py_compile $(find vmagent -name '*.py' | sort)
   grep -rn "os.getenv\|os.environ" vmagent/ --include='*.py' | grep -v config.py   # expect empty
   PYTHONPATH=. python3 -m pytest -q tests/test_<x>_adapter.py tests/test_http_error_factory_equivalence.py
   ```

   Live: the adapter surface is golden-exercised for storage/search/fabric/cosmos
   — a `GOLDEN_PATH_PROBE_OK` run drives storage blob discovery + search
   index/query + fabric/cosmos demo paths through the real adapters. Follow
   [regression_protocol.md](./regression_protocol.md) for deploy + live sweep.

## Hard rules

- **MI-only.** No keys, SAS, connection strings, or admin keys. The ONE
  documented exception: gremlin's flag-gated ARM `listKeys` data-plane auth
  (key material in memory only, never returned/logged/audited) — do not
  generalise it.
- **Zero public-contract change on a migration.** All `*ToolError` classes,
  every error-code string, all tool names, the `RegisteredTool`/`ToolDefinition`
  structure, the `registry_defs/*` handlers, the `module:function` loader
  manifest, and `invoke_tool`'s `str(exc).split(":",1)[0]` extraction stay
  byte-identical. Prove it with the §6 snapshot test.
- **`access_denied=False` is set ONLY for the discovery-wrapper case.** Do NOT
  flip the default for a new source unless its own wrappers string-match
  `{prefix}_http_401/403`.
- **The base owns transport + error ONLY.** No audit, no `card_kind`, no registry
  coupling in the adapter. `invoke_tool` is the single choke point.
- **SDK calls never go through `request()`.** Add a side-channel method (gremlin
  / search `_embed` precedent).
- `adapter_base.py` is FROZEN — extend behaviour via subclass hooks, not edits to
  the base.
