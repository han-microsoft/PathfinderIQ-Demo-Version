# AUTODEV — PathfinderIQ operational logbook

Brutal-honesty deploy/operations log for PathfinderIQ. Landmines, version pins,
auth recipes, and the dated increment ledger. Read this before deploying or
changing runtime behaviour. Lineage: GridIQ → vm_agent → PathfinderIQ.

Capability truth lives in [build_spec/CURRENT_STATE.md](build_spec/CURRENT_STATE.md).

---

## 0. Live deployment (2026-06-19)

| Field | Value |
|---|---|
| App | `ca-pfiq-336705e3` Container App |
| URL | https://ca-pfiq-336705e3.blackwave-122e19f0.eastus2.azurecontainerapps.io/ |
| Subscription | `67255afe-8670-4401-a1b8-df6ca63a3516` (ME-M365x21900035-hchoong-1) |
| RG | `rg-pathfinderiq-demo` (eastus2) |
| Model | Foundry `gpt-5.4` (deployment `gpt-5.4`), account `aif-1-personal`, RG `personal-llm` (eastus), project `proj-default` |
| Identity | UAMI `id-pfiq-336705e3` (client `ea8716ae-fdd9-4b2e-a133-6ef487d39b36`) |
| ACR | `acrpfiq336705e3` |
| Graph | Cosmos Gremlin `cosmos-pfiq-graph-336705e3` (db `pfiq`, graph `topology`) |
| Telemetry/Sessions | Cosmos NoSQL `cosmos-pfiq-sql-336705e3` (db `pfiq`: `alerts`,`telemetry`; db `sessions`: `conversations`) |
| Knowledge search | Azure AI Search `srch-pfiq-336705e3` (eastus) + Storage `stpfiq336705e3`; embed `text-embedding-3-small` on the Foundry |
| Auth | `AUTH_ENABLED=true` — Entra app reg `2640ff33-5352-48d7-ba43-92c157dd1a42`, tenant `c79ab2bb…` |

Project endpoint env: `AZURE_AI_PROJECT_ENDPOINT=https://aif-1-personal.services.ai.azure.com/api/projects/proj-default`.

---

## 1. Architecture change (Fabric → Cosmos, agentkit adoption)

This deploy retired the Fabric data backend and adopted the **agentkit** kernel:

- **agentkit vendored** at `app/backend/agentkit/` (domain-blind kernel from GridIQ). Tools consume its datasource adapters + error envelope.
- **Graph** → Cosmos DB Gremlin via agentkit `GremlinToolAdapter` (`tools/_cosmos.py` + `tools/graph_explorer/_cosmos_gremlin.py`). Agent emits Gremlin, not GQL.
- **Telemetry** → Cosmos DB NoSQL via a **new** agentkit `CosmosNoSqlToolAdapter` (`agentkit/tools/adapters/cosmos_nosql_adapter.py`) — the Cosmos-native analogue of GridIQ's `KqlToolAdapter`, returning the same `{columns,rows}` envelope. Agent emits Cosmos SQL, not KQL.
- Seeder: `graph_data/scripts/seed_cosmos.py` (CSV → Gremlin vertices/edges + NoSQL docs).

The deep `agentkit.core`/`sdk`/`hosting` runtime swap is **deferred (RED)** — see CURRENT_STATE.md D1. PathfinderIQ still runs its own `agents/_builder.py` over `AzureAIAgentClient` (MAF rc1). Swapping onto agentkit's rc4 SDK seam is a separate, regression-gated effort.

---

## 2. Landmines hit during this deploy (read before redeploying)

### L1 — scenario.yaml model overrides the env model
`agents/_builder.py` resolves the model as `model_override or agent_cfg["model"] or settings.llm_model`. The scenario's per-agent `model:` field **wins over** `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`. The scenario shipped `model: gpt-5.2` (not deployed on `aif-1-personal`), so `/api/config` reported `gpt-5.2` and chat would 404 the deployment. **Fix:** set every `model:` in `scenario.yaml` to `gpt-5.4`. There is no static env override for the per-agent model — it is baked into the image, so a model change needs a rebuild.

### L2 — backend-prompt placeholders inject the OLD query language
`agents/_prompts.py` resolves `{graph_backend_prompt}` → `query_language/gql.md` (GQL) and `{telemetry_backend_prompt}`/`{alerts_backend_prompt}` → the KQL prompts. After switching to Cosmos these inject **contradictory** GQL/KQL guidance. **Fix:** repoint `{graph_backend_prompt}` → `query_language/gremlin.md` (new) and rewrite `tool_query_telemetry.md`/`tool_query_alerts.md` to Cosmos SQL. Grep `agents/_prompts.py` after any backend swap.

### L3 — Cosmos Gremlin `valueMap('id','label')` returns empty id/label
In Cosmos DB Gremlin, `id` and `label` are NOT regular properties; `.valueMap('id','label')` yields `{'id': [], 'label': []}`. Use `.valueMap(true)` (includes id+label) or `.id()`/`.label()`. Prompt examples must not use `.valueMap('id','label')`.

### L4 — no direct Depot→TransportLink edge (dispatch traversal)
`services` edges run Depot→CoreRouter/AmplifierSite, never Depot→TransportLink. `g.V(link).in('services')...` returns empty. Correct fault→dispatch path hops via the link's routers: `g.V(link).out('connects_source','connects_target').in('services').in('stationed_at').hasLabel('DutyRoster')`. Documented in `graph_schema.md` + `tool_query_graph.md`.

### L5 — health endpoints are at `/health`, NOT `/api/health`
`health_router` is included **without** the `/api` prefix (`app/main.py`). nginx proxies a dedicated `location /health`. Probe `https://<fqdn>/health` and `/health/ready`. `/api/health` returns FastAPI 404. (The other routers ARE under `/api`.)

### L6 — credential MI detection missed Container Apps
`foundation/credentials.py` tier-2 only checked `WEBSITE_INSTANCE_ID`/`KUBERNETES_SERVICE_HOST`. Container Apps sets neither — it sets `CONTAINER_APP_NAME`/`CONTAINER_APP_ENV_DNS_SUFFIX`. Without the fix, `get_azure_credential()` fell through to `AzureCliCredential` (no `az` in container) → all Azure calls fail. **Fixed:** tier-2 now also checks the Container Apps env vars. Set `AZURE_CLIENT_ID=<UAMI clientId>` so `DefaultAzureCredential` binds the user-assigned identity.

### L7 — per-item Cosmos upsert is far too slow for bulk seed
Seeding 22.5k telemetry docs with sequential `upsert_item` at 400 RU crawled (~91 docs/min observed). **Fix:** parallelize with `ThreadPoolExecutor(32)` and bump container throughput (manual `--throughput 4000`). Note: switching a manual-throughput container to autoscale via `throughput update --max-throughput` errors — provision autoscale at create time or use manual `--throughput`. Full 22,584 docs then seed in ~1-2 min.

### L8 — nginx/container listens on 8080, target-port 8080
Despite header comments mentioning port 80, the image's nginx listens on `8080` (non-root) and `EXPOSE 8080`. Container App `--target-port 8080`.

### L9 — Foundry Agents API needs PROJECT-scope RBAC, not account-scope
`AzureAIAgentClient` calls the project-scoped Agents API (`/api/projects/proj-default/.../create_agent`). Granting the UAMI `Azure AI Developer` + `Cognitive Services OpenAI User` on the **account** scope is NOT enough — `create_agent` returns `401 PermissionDenied` (`aka.ms/FoundryPermissions`). **Fix:** assign the roles at the **project** resource scope:
`…/Microsoft.CognitiveServices/accounts/aif-1-personal/projects/proj-default`. Granted `Azure AI Developer` + `Cognitive Services User` + `Cognitive Services OpenAI User` there; chat then works (verified 5 tool calls, 0 errors). Allow a few minutes for RBAC propagation.

### L10 — Azure AI Search defaults to API-key-only data-plane auth
A fresh Search service rejects AAD tokens for index/datasource/indexer management — the provisioner fails with `Operation returned an invalid status 'Forbidden'` even with `Search Service Contributor` + `Search Index Data Contributor` granted. **Fix:** enable RBAC data-plane: `az search service update -n <svc> -g <rg> --auth-options aadOrApiKey --aad-auth-failure-mode http403`. Wait ~60s for propagation, then re-run provisioning.

### L11 — Search vectorizer assumes same-RG Foundry (cross-RG break)
`provision_search_index.py::_get_ai_services_resource_id()` built the Foundry ARM id from `AZURE_RESOURCE_GROUP`. The GPT-5.4 Foundry (`aif-1-personal`) lives in a different RG (`personal-llm`), so the vectorizer referenced a non-existent resource. **Fix (patched):** added an `AI_FOUNDRY_RESOURCE_GROUP` env override (defaults to `AZURE_RESOURCE_GROUP`). Set it to the Foundry's RG. Also grant the **Search service MI** `Cognitive Services OpenAI User` on the Foundry account (it embeds at index + query time). And: eastus2 was out of Search capacity — created the service in eastus.

### L12 — Search indexer "0 documents indexed" race
An indexer that runs immediately after blob upload can see an empty container (runbooks indexed 0/15). **Fix:** `reset_indexer()` + `run_indexer()` after the blobs are committed, or re-run the provisioner (idempotent). Verify with `SearchClient.get_document_count()`.

### L13 — agentkit-ui vendoring: peer-dep + version traps
Adding `packages/agentkit-ui/src` to the frontend `tsconfig` `include` makes the kit part of `tsc` (so the Docker `npm run build` type-checks it). It pulls 3 deps not in PathfinderIQ: `react-resizable-panels` (**must be `^4.7.3`** — v2/v3 dropped the `Group`/`Separator` exports the kit imports), `react-day-picker@^9`, `date-fns@^4`. Add all three to `package.json` (so `npm ci` in the image gets them) before building.

### L14 — az CLI active subscription drifts to the GridIQ sandpit
`az acr build` failed with `acrpfiq336705e3 … could not be found in subscription 'Sandpit Non-Production (af9ce6a9-…)'` — the CLI active subscription had drifted back to GridIQ's `af9ce6a9-…`. **Always `az account set --subscription 67255afe-…` immediately before any `az acr build` / deploy** for this project. (Same class as the user-memory azure-deploy note.)

### L15 — Cosmos public network access disabled by subscription governance
The live app started returning **503** on `POST /api/sessions`; `/health` (GET, no Cosmos) stayed 200. Root cause: both Cosmos accounts had `publicNetworkAccess: Disabled` — the Container App (no VNet) is a public client, so Cosmos firewall returned `403 Forbidden` (`Request originated from IP … through public internet … blocked by your Cosmos DB account firewall`). It worked at first, then a **subscription governance policy disabled public access post-creation**. **Fix:** `az cosmosdb update -n <acct> -g <rg> --public-network-access Enabled` on BOTH the Gremlin + NoSQL accounts (retry through the `operation in progress` exclusive-lock). For a durable fix, VNet-integrate the Container App env + private endpoints. Symptom signature: signed/authed POSTs 503 while unauth POSTs correctly 401.

### L16 — `in` is a reserved word in Cosmos's Groovy Gremlin parser
Investigation queries failed live with `GraphSyntaxException: Unexpected token: ')'`. Root cause: a **bare anonymous `in('label')` step** (inside `project()/by()/where()`), e.g. `.by(in('amplifies').valueMap(true).fold())`. Cosmos's Groovy-based Gremlin parser treats `in` as a reserved keyword, so the bare anonymous form is rejected — while `out('label')` works because `out` is not reserved. **Fix:** anonymous `in` steps must use the `__.in(...)` form. Enforced centrally by a sanitizer in `tools/_cosmos.py::_sanitize_gremlin_reserved` (regex `(?<![\w.])in\s*\(` → `__.in(`) that runs first in `_transform_gremlin`, so LLM-emitted queries are auto-corrected. The lookbehind preserves `within(` and top-level `.in(`; the rewrite is idempotent. Regression test: `tests/unit/test_cosmos_guards.py::TestGremlinReservedWordSanitizer`.

---

## 3. Auth / identity recipes

- App data-plane auth = **managed identity only** (no keys/SAS). UAMI `id-pfiq-336705e3`.
- Cosmos data-plane RBAC is NOT ARM RBAC — use `az cosmosdb sql role assignment create` with built-in Data Contributor `00000000-0000-0000-0000-000000000002`, scoped to the account, for BOTH the Gremlin and NoSQL accounts. (Gremlin API accounts use the same SQL data-plane role assignments.)
- Foundry access (cross-RG to `personal-llm`): grant the UAMI `Cognitive Services OpenAI User` **and** `Azure AI Developer` on the `aif-1-personal` account scope. (`Azure AI User` is not a valid role name.)
- ACR pull: `AcrPull` on the ACR + `--registry-identity <uami-resource-id>` on the Container App.
- Token scope for Cosmos Gremlin: `https://cosmos.azure.com/.default` (agentkit `GremlinToolAdapter` default).

---

## 4. Deploy recipe (from zero)

```bash
SUB=67255afe-8670-4401-a1b8-df6ca63a3516; RG=rg-pathfinderiq-demo; LOC=eastus2
az account set --subscription "$SUB"
az group create -n "$RG" -l "$LOC"
# Cosmos Gremlin (graph) + NoSQL (telemetry/sessions)
az cosmosdb create -n cosmos-pfiq-graph-<sfx> -g "$RG" --locations regionName=$LOC --capabilities EnableGremlin
az cosmosdb create -n cosmos-pfiq-sql-<sfx>   -g "$RG" --locations regionName=$LOC
# ... gremlin db/graph + sql db/containers (see seed_cosmos.py header) ...
# UAMI + ACR + Container Apps env
az identity create -n id-pfiq-<sfx> -g "$RG"
az acr create -n acrpfiq<sfx> -g "$RG" --sku Basic
az containerapp env create -n cae-pfiq-<sfx> -g "$RG" -l "$LOC"
# RBAC (see §3). Seed:
python3 graph_data/scripts/seed_cosmos.py --gremlin-endpoint wss://... --nosql-endpoint https://... \
  --scenario-dir graph_data/data/scenarios/telecom-playground-v2 --wipe
# Build + deploy
az acr build --registry acrpfiq<sfx> --image pathfinderiq:<tag> --file Dockerfile.unified .
az containerapp create -n ca-pfiq-<sfx> -g "$RG" --environment cae-pfiq-<sfx> \
  --image acrpfiq<sfx>.azurecr.io/pathfinderiq:<tag> --registry-identity <uami-id> --user-assigned <uami-id> \
  --target-port 8080 --ingress external --min-replicas 1 --max-replicas 1 \
  --env-vars LLM_PROVIDER=agent AZURE_AI_PROJECT_ENDPOINT=... AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=gpt-5.4 \
    SCENARIO_NAME=telecom-playground-v2 AUTH_ENABLED=false AZURE_CLIENT_ID=<uami-client> COSMOS_GREMLIN_ENDPOINT=... ...
# Verify
curl -s https://<fqdn>/health/ready
```

Redeploy a new image: `az acr build ...` then `az containerapp update -n ca-pfiq-<sfx> -g "$RG" --image <acr>/pathfinderiq:<tag>`.

---

## 5. Version pins

- `gremlinpython==3.8.1` (Cosmos Gremlin; other versions rename `GraphSONSerializersV2d0`).
- `azure-cosmos>=4.9.0`.
- `agent-framework==1.0.0rc1` (+ `azure-ai-agents`/`azure-ai-projects`). agentkit's SDK seam expects rc4 — do NOT bump without the deep-runtime-swap regression loop (CURRENT_STATE D1).

---

## 6. Increment ledger

### 2026-06-19 — Cosmos migration + agentkit adoption + first deploy to rg-pathfinderiq-demo
- Vendored agentkit; added `CosmosNoSqlToolAdapter`.
- Rewrote graph tool → Cosmos Gremlin (`GremlinToolAdapter`); telemetry/alerts → Cosmos NoSQL.
- Added `seed_cosmos.py`; seeded 90 vertices / 122 edges + 3,669 alerts + 22,584 telemetry docs from the telecom scenario CSVs.
- Provisioned RG + 2 Cosmos accounts + UAMI + ACR + Container Apps env; full MI RBAC.
- Wired GPT-5.4 (`aif-1-personal/proj-default`) via managed identity; `AUTH_ENABLED=false`.
- Landmines L1–L8 above. App live + `/health/ready` green.
- Added `build_spec/CURRENT_STATE.md` ledger + this AUTODEV.

### 2026-06-19 — Deferrals pass (D2–D5 performed; D1 reasoned-deferred)
- **D4 AI Search** — Search `srch-pfiq-*` (eastus) + Storage `stpfiq-*` + `text-embedding-3-small` on the Foundry; 4 indexes provisioned + indexed (runbooks 60 / tickets 21 / equipment 20 / infra-specs 30 chunks); hybrid vector+semantic verified; live `search_runbooks` via KnowledgeAnalyst cited the fibre-cut runbook (0 error envelopes). Landmines L10–L12.
- **D5 Capability fabric** — ported vm_agent's catalog: `app/capability/{search,build}` + `find_capabilities` tool + `/api/catalog[/search]`; 22 entries; ranked search live.
- **D3 Entra auth** — app reg `2640ff33…` (SPA redirect + `access_as_user`); `AUTH_ENABLED=true`; unauth `/api/sessions`→401; `/api/auth_setup`→useLogin:true. Landmine L9.
- **D2 agentkit-ui** — vendored + `@agentkit-ui/*` alias + deps; type-checked + bundled; runtime adoption seam (`src/integrations/agentkitUi.ts`). Landmine L13.
- **D1** deep runtime swap + MAF rc4 — reasoned-deferred (CURRENT_STATE D1) to protect the shared live deploy.

### 2026-06-19 — Lineage improvements pass (GridIQ/vm_agent ports)
- **Dev-sign side-channel** (C13) — mounted agentkit's `install_signed_request_auth`; `auth.py` honours the `devauth_user` scope; pubkey in `DEV_PUBLIC_KEY_ED25519`. Lets headless probes drive the auth-gated app.
- **SSE contract probe** (C14) — `scripts/sse_contract_probe.py` signs via dev-sign + asserts the wire contract.
- **Capability fabric multi-kind** (C15) — skills (`*.skill.md`) + recipes (`*.recipe.yaml`) discovered into the catalog; seeded `fault_triage`, `blast_radius`, `full_incident_investigation`.
- **Deploy guardrails** (C16) — `deploy_app.sh` env preflight + auth-gate auto-disable.
- **Audit finding** — 49 `os.getenv` reads outside config/credentials; the bulk are in the now-dead Fabric tool modules (`tools/_fabric_*`, `graph_explorer/_fabric`, `telemetry/_fabric|_alerts`) still referenced by `scenario/_registry` + health/observability routers — a cascading removal scoped as follow-up (not done mid-session to protect the live deploy). Landmine L14.
- Reasoned-remaining: full agentkit-ui component migration; agentkit run-engine swap (D1); dead-Fabric removal + full getenv centralisation.

### 2026-06-20 — Housekeeping loop (golden-path-gated)
- **Baseline** locked on the signed SSE contract probe (`SSE_CONTRACT_OK`). Hit + fixed L15 (Cosmos PNA) before the loop could start — the codebase can't be cleaned on a broken base.
- **Batch 1 (dead-Fabric removal)** — removed the retired Fabric data-plane stack now that Cosmos backs graph+telemetry: `tools/{_fabric_auth,_fabric_constants,_fabric_throttle,_query_guardrails}.py`, `tools/graph_explorer/_fabric.py`, `tools/telemetry/{_fabric,_alerts}.py`, and the stale `query_language/gql.md` prompt. Rewired `app/scenario/_registry.py` (Fabric → `cosmos_gremlin` backend; `get_fabric_throttle_status()` → None hook, routers behaviour-preserved) + `tools/__init__.py` package map. Reachability proven (`_query_guardrails` imported only by the deleted Fabric tools; `_spoof_state` kept — live). **Metric delta: 121→114 files (−7), 17,795→16,565 LOC (−1,230, −7%).** Golden path held.

### 2026-06-20 — Runtime scenario swap (modular use-case packs) — C18
- **Goal** — prove an entire use-case (agents + prompts + tools + datasource + topology) swaps at runtime over a constant backend core, with a frontend mechanism, verified by regression.
- **Found** — the read layer was already swap-shaped: `RequestScope.scenario_name` + per-request `get_scenario_dir`/`load_scenario_yaml`/`load_topology`. Middleware *documented* 3-tier resolution but only read the env var; frontend `authHeaders()` *documented* `X-Scenario-Name` but never sent it. A pre-existing-but-unfinished per-user-preferences feature had tests (`tests/isolation/`, `test_scenario_*`) but no backend.
- **Built** — backend: `app/scenario/_catalog.py` (on-disk pack discovery), `GET /api/scenarios` + `POST /api/scenarios/select` + `GET /api/preferences`, `app/services/preferences.py` (`InMemoryPreferencesStore` on `app.state.preferences`, env-seeded, OID-keyed, restart-reset), middleware 3-tier resolve (header→user-pref→env, each fresh `get_scenario_dir`-validated), cloud-free `tools/sandbox.py`. Frontend: `stores/scenarioStore.ts`, `X-Scenario-Name` injected in `api/client.ts::authHeaders`, `components/layout/ScenarioSwitcher.tsx` in the Header. Second pack `graph_data/data/scenarios/demo-sandbox/` (static dataset, 2 agents, no Azure). Tooling: `provision_scenario.py`, `validate_scenario.py` (P0).
- **Regression** — `test_scenario_swap_proof.py` 6/6 (catalog lists both, header rebinds metadata+agents+topology, sandbox tool reads bundled data, A↔B stable); isolation + scenario suites 18/18 + 23/23; frontend `npm run build` green. Pre-existing failures (session/multi-agent/agent-prompt + 4 dead-Fabric-import collection errors) confirmed identical with changes git-stashed → **zero added regressions**.
- **Landmines:**
  - **L16 — `load_scenario_yaml`'s `@lru_cache(maxsize=4)` was keyed on the raw `None` arg.** A no-scope startup call cached `{}` under `None`, then every later `load_scenario_yaml()` returned `{}` → the scenario-metadata endpoint silently went "unregistered" for ALL scenarios. **Fix:** resolve the name first, delegate to `_load_scenario_yaml_cached(name)` keyed by the *resolved* name. Any swap-era per-request cache MUST key by resolved scenario, never the call argument.
  - **L17 — graph_schema.yaml has ONE canonical shape: `vertices:`/`edges:` are LISTS of dicts** (`label`, `csv_file`, `id_column`, `partition_key`, `properties:[...]`), consumed by BOTH the seeder and `_metadata._load_graph_schema_summary` (which does `v.get("label")`). A dict-of-dicts form 500s `/api/scenario`. New packs must copy the list form.
  - **L18 — scenario-validation must use a FRESH on-disk check, not a cached allowlist.** A cached catalog (`lru_cache`) hid test-created/temp packs → header rejected → fell back to env. Middleware + `select` now validate via `get_scenario_dir()` (fresh `is_dir` + path-traversal guard); catalog scan is uncached.
- **Deferred (unchanged):** real-data ingest (RouteNet/SNDlib + 3GPP KB) drops into the same pack contract via a source-adapter; P2 datasource-binding move into the manifest (`data_sources.graph`/`telemetry`) is declared in `demo-sandbox` but tools still read `settings.*` for the Cosmos packs — full per-scenario binding is the next runtime step (see `build_spec/orchestrator_20260620_scenario_packs.md`).

### 2026-06-20 — Swap hardening pass (P2 bindings + perf + dead-test purge + live deploy)
- **P2 per-scenario Cosmos bindings (DONE).** `RequestScope` now carries `cosmos_graph_config` + `cosmos_telemetry_config` extracted from the manifest `data_sources.graph`/`telemetry` (`_extract_cosmos_config`). The 3 resolver seams in `tools/_cosmos.py` (`_resolve_gremlin_target`/`_resolve_telemetry_target`/`_resolve_alerts_target`) now read the active scenario's db/graph/container, falling back to `settings.*` when empty (endpoint+creds stay account-global). Packs can target separate Cosmos namespaces with no env change; telecom (no block) keeps `pfiq`. Test: `test_scenario_swap_proof.py::TestPerScenarioCosmosBinding`.
- **Perf.** Replaced the single-entry `_cached_scope` (which thrashed on alternating-scenario load) with a bounded per-scenario dict cache (`_scope_cache`, max 8) in `app/_middleware.py`. Scope build (yaml parse + config extraction) now amortized per scenario, not rebuilt on every A/B swap.
- **Dead-test purge (bug-free collection).** Removed 4 obsolete Fabric-era unit modules importing deleted `tools._fabric_*`/`tools.*._fabric` (`test_error_sanitization`, `test_guardrails`, `test_query_guardrails`, `test_throttle_gate`) + the `TestKQLReadOnlyGuardrail` (test_audit_phase2) + `TestHalfOpenProbeLogic` (test_audit_phase1) classes. Added `tests/unit/test_cosmos_guards.py` covering the LIVE Cosmos Gremlin/SQL read-only guards + limit/TOP injection. `pytest tests/` now collects with **zero import errors**.
- **Test isolation.** Added an autouse teardown fixture (`tests/conftest.py::_reset_process_swap_state`) clearing the scope cache + per-user preferences + agent-config cache between tests (shared-app singleton hygiene).
- **Landmine L19 — shared-app test harness pollution (pre-existing, NOT swap logic).** `tests/` reuse one `app` singleton; cross-module `app.dependency_overrides`/lifespan state leaks make some suites order-dependent (`session_lifecycle`/`health`/`multi_agent` fail even *alone* = pre-existing broken; `page_refresh_isolation` passes alone, fails in full-suite from override leak). Verified my changes add **zero** net failures via `git stash` baseline comparison. Swap correctness proven by per-module isolation + live probe, not the polluted full-suite count.
- **Live verify.** `scripts/scenario_swap_probe.py` (signed, dev-sign) asserts catalog lists both packs, header rebinds metadata+agents, per-user select round-trips, and the demo-sandbox cloud-free tool answers a live chat. Deployed image `pathfinderiq:20260620-174402-swap` to `ca-pfiq-336705e3` (ACR run ch7). **Results:** `SWAP_PROBE_OK` (11/11 checks) + telecom `SSE_CONTRACT_OK` (2 graph tool calls, terminal `done`, 0 errors) — P2 bindings did not regress the live Cosmos path.

### 2026-06-20 — Foundation strengthening + UI polish pass
- **Docs.** README gained a **Runtime Scenario Swap** section (3-tier resolution, endpoints, `scenario_swap_probe.py`) and the "Adding a New Scenario" steps were rewritten Fabric→Cosmos with `validate_scenario.py` + `provision_scenario.py`.
- **Foundation (config boundary, swap-strengthening).** Centralized the operator-default scenario to a single source of truth: removed 3 redundant `os.environ.get("SCENARIO_NAME", …)` reads (`app/_middleware.py`, `app/services/preferences.py` ×2, `app/foundation/request_scope.py`) — `settings.scenario_name` already binds `SCENARIO_NAME` (pydantic `env_prefix=""`). Made the **telecom pack self-declare** its Cosmos bindings (`data_sources.graph`/`telemetry` = pfiq/topology/telemetry/alerts, matching the operator defaults → no behaviour change) so every pack exercises the P2 binding path, not just demo-sandbox.
- **Deferred foundation (documented, not done — higher risk/lower swap-relevance):** `routers/config.py` reads ~13 env vars directly incl. stale Fabric flags (`FABRIC_WORKSPACE_ID`/`FABRIC_TENANT_ID`); `foundation/retry.py` + `boot_validation.py` env reads. Frontend `/api/config` coupling makes a response-shape change non-trivial — scope as a separate config-centralization slice.
- **UI polish (on-system, branding preserved).** (1) `ScenarioSwitcher` now renders through the shared branded `SelectorDropdown` (matches model/theme chrome + a "Switching…" indicator during the swap reload) instead of a raw `<select>`. (2) Chat input border/focus moved off hardcoded `border-white/10` (near-invisible in the **light MSIQ theme**) to on-system `border-border` + a `focus-within:ring-brand/40` accessibility ring. (3) `ThinkingDisplay` accent bar → theme-correct `border-border` + brand left accent. All MSIQ branding/logos/names (Foundry IQ, Fabric IQ, WorkIQ, Azure AI Search) preserved.
- **Verify.** Backend swap/isolation/guard suites 41/41; `validate_scenario.py --all` OK; frontend `npm run build` green (4594 modules, tsc clean). Deployed image `pathfinderiq:20260620-180802-polish`; live swap + SSE probes re-run post-deploy.

### 2026-06-20 — Browser render-acceptance harness (no-auth path) + dev-sign scope clarification
- **dev-sign scope (clarified).** The Ed25519 dev-sign side-channel signs **API requests** — it drives the backend contract (proven: `SWAP_PROBE_OK` + `SSE_CONTRACT_OK` against `AUTH_ENABLED=true`). It does **NOT** give the browser SPA a session: the SPA acquires an MSAL bearer via `getAccessToken()`, and this repo has **no Playwright/e2e dev-sign browser fixture** (no `app/frontend/e2e/`). So pointing a browser at the deployed `AUTH_ENABLED=true` app hits the MSAL login gate.
- **Render-acceptance recipe (no cloud, no auth — use this to visually verify UI changes).** The SPA renders the full shell when `/api/auth_setup` returns `useLogin:false`, and the scenario catalogue/agents/topology endpoints need **no Cosmos** (catalogue scans disk packs; topology reads `topology.json`):
  ```bash
  # backend (echo LLM, auth off) on the vite proxy target port 9000
  cd app/backend && AUTH_ENABLED=false LLM_PROVIDER=echo SCENARIO_NAME=<pack> \
    OTEL_EXPORT_TARGET="" python3 -m uvicorn app.main:app --host 127.0.0.1 --port 9000 &
  # frontend dev server (proxies /api -> :9000)
  cd app/frontend && npm run dev &   # http://localhost:5173
  ```
  Then drive `http://localhost:5173` with the browser tools. **Verified live (2026-06-20):** MSIQ branding intact (Pathfinder IQ + Foundry IQ / Fabric IQ / WorkIQ logos, "Asia AI Apps GBB"); the polished on-system `ScenarioSwitcher` ("USE CASE" dropdown) renders both packs; and a **full swap renders end-to-end** — restarting the backend with `SCENARIO_NAME=demo-sandbox` rebound the sidebar to **SandboxGuide + SandboxAnalyst** agents and the graph to **4 nodes / 2 edges** (telecom was 5 agents, 90/111), over the constant core.
- **Landmine L20 — native `<select>` can't be driven by the browser click tools.** The OS renders the option list in a layer Playwright snapshots don't capture; `selectOption` is not exposed. To demonstrate a swap in-browser, change the backend's operator-default scenario (or pre-seed `localStorage['selected-scenario']`) and reload, rather than clicking the dropdown.
- **Gap that remains (only this).** The real **MSAL interactive login** click-through (Entra credentials/MFA) is not automatable headlessly — auth machinery, not feature behaviour; verified at the contract layer instead (unauth→401, signed→works).

### 2026-06-21 — UX polish tranches 1-3 (live-verified, branding preserved)
- **T1 — robustness/first-run.** `WelcomeOverlay` now **honors `localStorage['welcome-dismissed']` on mount** (the documented check was never implemented → it re-gated on every load, incl. every scenario-swap reload). Returning users/swap-reloads land directly in the app. Responsive headings (`text-3xl sm:text-5xl`, `flex-wrap`, `min-w-0`) fix the "Pathfinder IQ" off-screen clip at narrow widths. Intro **✕ now closes to the app**; **Esc** closes the overlay. `ToolCallDisplay` header/detail padding standardized to `px-3 py-2.5`.
- **T1 — verified clean (no change):** focus rings are already global (`index.css *:focus-visible { ring-2 ring-brand }`); the only remaining hardcoded `white/`-opacity utils are on colored backgrounds (brand button text, color swatches) where white/black hairlines are correct — no theme breakage. Replay tour overlay already responsive (`max-w-xl px-4`).
- **T2 — IA/chat polish.** Sidebar sections (Settings/Styles/Language/Development) were **already `collapsible defaultCollapsed`** — verified clean, no refactor needed. Chat: tightened empty-state spacing (`gap-3`, `h-10` icon), animated the inline "Loading…", `animate-fade-in` on the scroll-to-bottom button. Multiple demo entry points left intact (intentional for a showcase demo).
- **T3 — perf/a11y.** **Bundler chunk-splitting** (`vite.config.ts` `manualChunks`): the **1.75 MB single entry chunk → 251 KB** app entry + parallel-cacheable vendor chunks (syntax 634 / vendor 422 / msal 290 / markdown 135 / graph 106 / motion 31 KB). Esc-to-close on the welcome overlay. (Deferred: per-overlay focus-trap + contrast tuning — needs a dedicated a11y pass with visual iteration.)
- **Verify.** `tsc` clean; `npm run build` green (entry 251 KB). Browser render acceptance (no-auth path) confirmed **A3 live** — app renders directly with no overlay gate, sidebar clean, branding intact (Pathfinder IQ / Foundry IQ / Fabric IQ / WorkIQ / Asia AI Apps GBB). Deployed image `pathfinderiq:20260621-001548-ux`; live swap + SSE probes re-run post-deploy.

### 2026-06-21 — Housekeeping + foundation-strengthening: dead-Fabric surface removal
- **Survey** (golden-path baseline green on the UX image). Backend 118 files / 16,997 LOC; oversized modules `services/session_store/cosmos.py` (752), `routers/chat.py` (559), `auth.py` (508) — flagged, left (DAA/choke, high-risk). Top finding: **dead Fabric residue** still live after the Cosmos migration (tools were removed earlier; the health/config surface remained).
- **Batch (AMBER, proven-orphan): removed the dead Fabric backend surface.** `routers/service_health.py::_check_fabric` (pinged the retired Fabric data plane → showed "Fabric: disconnected" in the demo's Service Health panel) + its rollup entry; `foundation/config.py` `fabric_*` fields; `foundation/request_scope.py` `FabricServiceConfig` + `fabric_config` scope field + `_extract_fabric_config` (no runtime reader — only a docstring example); `routers/config.py` `fabric_available`/`cross_tenant`/`fabric_graph`/`fabric_telemetry`/`cross_tenant_fabric` flags; frontend `ServiceHealth.tsx` `SERVICE_META.fabric`. **Reachability proven** (grep-clean of `FabricServiceConfig`/`_check_fabric`/`_extract_fabric_config`/`settings.fabric_*`/`.fabric_config`). Left `credentials.py` `require_fabric_sp` + `FABRIC_*` SP tier (RED/auth — deferred). **Metric: 16,997 → 16,844 LOC (−153).** Fabric IQ **branding preserved** (theme, replay tour, logos, login — untouched).
- **Verify.** `py_compile` clean; affected pytest 38 passed (incl `test_scenario_swap_proof`); frontend `tsc` + `vite build` green. Deployed `pathfinderiq:20260621-003342-housekeep`. **Live: `fabric` removed from `/api/services/health`** (now `ai_foundry`/`ai_search`/`cosmos_sessions`/`session_store`) ✓; all read-path golden checks pass (catalog/metadata/agents/scenario/select).
- **L21 — live session-create blocked by EXTERNAL infra change (NOT this batch).** Mid-verification, `/health/ready` went 503: `session_store: "Session store temporarily unavailable"`. Root cause: **`cosmos-pfiq-sql-336705e3` AND `cosmos-pfiq-graph-336705e3` had `publicNetworkAccess: Disabled`** (vnet:false, no private endpoint) → Container App can't reach the data plane → Cosmos query `403 Forbidden` (Server: Compute) → `cosmos_sessions` breaker opens → `POST /api/sessions` 503. UAMI Cosmos SQL Data Contributor role IS correctly assigned (account scope) — so this was a **network-access change**, external to and independent of the code (session-create worked on the UX image ~40 min prior; PNA defaults to Enabled at create, so an external process/policy toggled it Disabled). **RESOLVED 2026-06-21:** `az cosmosdb update -n <acct> -g rg-pathfinderiq-demo --public-network-access ENABLED` on **both** Cosmos accounts (persists — permanent), then `az containerapp revision restart` to reset the open breaker. Golden path then GREEN: `SWAP_PROBE_OK` (11/11 incl. session-create + chat) + telecom `SSE_CONTRACT_OK` + KnowledgeAnalyst `SSE_CONTRACT_OK` (7 search tool calls). **Permanence:** PNA-Enabled is the account default; add `--public-network-access Enabled` to the `az cosmosdb create` steps in §4 to harden against re-provisioning, and watch for any Azure Policy that auto-disables public access on this sub.
- **L22 — `ai_search` shows "down" in Service Health but knowledge search WORKS (false-negative).** The health probe does `GET /indexes?$select=name` (lists index *definitions*) which needs a broader role (Search Service Contributor / Index Data Contributor); the UAMI has **Search Index Data Reader**, which covers document **search** (what the agents actually use) but not listing index defs → health pings 403 while `search_runbooks`/`search_tickets` succeed live (verified: KnowledgeAnalyst probe, 7 tool calls, 0 errors). Search service config is correct (`authOptions: aadOrApiKey`, `disableLocalAuth:false`, `pna:Enabled`). Optional fix: grant the UAMI `Search Index Data Contributor` (clears the false-negative) OR change `_check_ai_search` to a doc-search ping instead of list-indexes. Cosmetic — does not affect the demo.
- **L14 recurrence — the CLI active subscription drifted to the GridIQ sandpit (`af9ce6a9-…`) twice this session**, breaking `az containerapp update` ("does not exist") and `az search service show`. Re-pin `az account set --subscription 67255afe-…` immediately before EVERY az op, not just builds.

## 2026-06-21 — Onboarded 3rd scenario `oran-5g-ran` (O-RAN 5G RAN), all 3 cloud surfaces live + swappable

- **What.** Second real-domain pack beyond telecom: an O-RAN 5G RAN slice-SLA-breach scenario (gNB→CU→DU→Cell→Slice→UE hierarchy + per-slice/cell/UE KPM telemetry + synthesised alarm stream + O-RAN/3GPP knowledge base). Demo-grade synthetic data modelled on the ColO-RAN open-dataset structure (per `OPEN_TELCO_DATASETS.md`); real CSVs are a drop-in via the same schema.
- **Keystone — generalized the seeder.** `graph_data/scripts/seed_cosmos.py` gained `--schema-driven`: graph from the pack's `graph_schema.yaml` (`vertices` + `edges`, endpoints matched by CSV column), telemetry from a new `telemetry_schema.yaml` (`sources:` CSV→container with `id_column`/`id_template`/`entity_column`→`entityId`/`kind`). Additive — telecom keeps the legacy hardcoded path (default). New datasets seed with zero seeder edits.
- **Pack.** `graph_data/data/scenarios/oran-5g-ran/` cloned from telecom (guarantees all prompt/UI/replay files exist) then data + domain content replaced. Generators: `scripts/generate_oran_dataset.py` (deterministic, seed 424242 → 261 vertices/534 edges, 3600 KPM rows, 45 alarms, topology.json), `scripts/generate_oran_knowledge.py` (18 KB docs across runbooks/tickets/equipment/infra_specs). Agents: `RANOrchestrator`/`RANInvestigator`/`KnowledgeAnalyst` reuse the scenario-agnostic graph/telemetry/search tools (bind per-scenario via P2). Manifest declares own Cosmos `oran` namespace + `oran-*` Search indexes.
- **Azure.** New `oran` Gremlin db+graph (pk `/pk`, 400 RU) + NoSQL db+containers (`telemetry` pk `/entityId` 1000 RU, `alerts` pk `/SourceNodeId` 400 RU) in the EXISTING accounts. 4 AI Search indexes via `azureaisearch/deploy_scenario.py --upload-files`. Image `pathfinderiq:20260621-oran` (Dockerfile L104 `COPY graph_data/data/` bakes the pack). Live: `SWAP_PROBE_OK` (catalog lists 3 packs) + O-RAN probe green (metadata/agents rebind; NI ran graph+telemetry+alerts; KA ran 3 search tools).
- **L23 — telecom `graph_schema.yaml` edge labels are STALE vs the live graph; do NOT switch telecom to `--schema-driven`.** The seeder's hardcoded telecom path uses edge labels (`connects_source`/`services`/`stationed_at`…) that telecom's prompts query; `graph_schema.yaml` (Fabric-era) declares different labels (`connects_to`…). Schema-driven seeding telecom would relabel edges and break its queries. New packs author self-consistent `graph_schema.yaml` labels = prompt labels. Generalization is additive, not a telecom migration.
- **L24 — schema-driven telemetry seeder needs its own 429 retry.** The legacy `seed_telemetry` had retry; the new `seed_telemetry_schema_driven` did not → at low container RU the 2304 UE-KPM upserts 429'd. Added per-doc `CosmosHttpResponseError.status_code==429` retry (honors `retry_after`, 16 threads). Provision telemetry containers ≥1000 RU during seed.
- **New-pack provisioning recipe (repeatable).** (1) author pack (`scenario.yaml` data_sources → own db/index names, `graph_schema.yaml`, `telemetry_schema.yaml`, `search_manifest.yaml`, prompts, generate data+topology); (2) `validate_scenario.py --scenario <n>`; (3) local catalog/agent-build smoke (`PYTHONPATH=app/backend … load_instructions+resolve_tools`); (4) re-pin sub; create Cosmos db/containers (mirror pk paths `/pk`,`/entityId`,`/SourceNodeId`); (5) `seed_cosmos.py --schema-driven` graph then telemetry; (6) write `graph_data/azure_config.env` (AI_SEARCH_NAME, STORAGE_ACCOUNT_NAME, AI_FOUNDRY_NAME, EMBEDDING_MODEL/DIMENSIONS) + `azureaisearch/deploy_scenario.py --upload-files`; (7) ACR build + `containerapp update`; (8) live swap probe with `X-Scenario-Name`. Embedding vectorizer reuses `aif-1-personal` `text-embedding-3-small` (1536d) — Search MI already has access. `{alerts_backend_prompt}`/`{telemetry_backend_prompt}` resolve to `tool_query_alerts.md`/`tool_query_telemetry.md` — do NOT also list those files explicitly (duplicates the prompt).

## 2026-06-21 — O-RAN multi-class incident battery + PathfinderIQ eval harness (GridIQ-lineage)

- **Why.** A single demo incident proves the plumbing, not the value. Ported the GridIQ constructor-harness idea (battery of falsifiable cases across distinct event classes + held-out split) to PathfinderIQ.
- **Data battery.** Rewrote `scripts/generate_oran_dataset.py` as an incident-registry generator: 6 independent incidents at disjoint sites/times across distinct classes — `fronthaul_degradation→URLLC SLA breach` (MEL, CRITICAL), `pci_collision` (SYD, no transport fault), `midhaul_congestion` (BNE, whole-DU uniform), `mmtc_signaling_storm` (PER, slice isolation holds), `backhaul_flap` (SYD-02, intermittent gNB-wide), `demand_congestion` (BNE-02, no fault) — plus benign baseline `CLOCK_DRIFT` (the "don't over-alarm" guard). Entities/topology deterministic + unchanged → **only telemetry/alarms re-seeded** (76 alarms, 11 classes); **no image rebuild** (runtime reads Cosmos; topology.json + pack prompts unchanged).
- **Harness.** `graph_data/eval/cases.yaml` (7 cases, gate observables as OR-synonym lists, `split: train|held_out`) + `graph_data/eval/run_eval.py` (thin PathfinderIQ adapter + runner; reuses `agentkit.dev_tools.dev_sign`, signs `X-Scenario-Name`, serial). Scores Gate-1 detection + Gate-2 investigation + Gate-3 recommendation by observable-token coverage; flags over-reach. `--rescore` recomputes verdicts/SUMMARY from saved transcripts offline (no live calls). Writes per-case JSON + `results/SUMMARY.md`.
- **Result (live, networkInvestigator, 1 run/case).** **7/7 pass · held-out 3/3** after scorer hardening. Each case: 8–12 tool calls, 27–49 s. Orchestrator full-flow on the flagship case scored the complete Gate-3 synthesis (root cause DU-MEL-01-2, exact cells, SL-URLLC-01/SmartGridCo, 12.79–13.43 ms vs 5 ms SLA, USD 5,000/hr, contained blast radius).
- **L25 — token scorers are negation-blind + tokenization-brittle; harden before trusting over-reach flags.** First run mis-scored 2 correct answers as `partial`: forbidden `critical` matched "act if it becomes MAJOR/**CRITICAL**" (a future *trigger threshold*, not a claim) and forbidden `fronthaul degradation` matched "**ruled out** ... fronthaul degradation"; G3 `load balanc` missed "load-**balancing**" (hyphen). Fixes (general): (1) `_norm` maps `-`/`/`→space so hyphen/slash variants match; (2) `_forbidden_hits` is negation-aware (skips a forbidden phrase if a negation cue — no/not/ruled out/without/within tolerance/… — appears within ~45 chars before it); (3) over-broad forbidden tokens are a *case-authoring* defect — `critical` was too generic for a benign case, replaced with specific over-reach phrases (`escalate to P1`, `dispatch`). Mirrors GridIQ's "a flag is a hypothesis, not a verdict."

## 2026-06-21 — O-RAN incidents made dropdown-triggerable (DemoFlowPicker)

- **What.** Added a `demo_flows:` block (7 flows) to `oran-5g-ran/scenario.yaml` mapping the eval battery to the chat **Demo Flows** dropdown (the same `DemoFlowPicker` the telecom "Sydney" pack uses). Flow ① (URLLC SLA breach) is a 3-step guided path (investigate → quantify $/hr → remediate) meant to run on the `orchestrator` agent; ②–⑦ are one-click investigations on `networkInvestigator`. Step-1 prompts are the proven harness seeds, so the dropdown reproduces the 7/7 battery behaviour live.
- **Pipeline.** `demo_flows` is pack data baked into the image (Dockerfile `COPY graph_data/data/`) → surfaced by `app/scenario/_metadata.py::_extract_demo_flows` → `/api/scenario` → frontend `ChatInput`→`DemoFlowPicker`. Required an image rebuild + deploy (`pathfinderiq:20260621-oran-flows`), unlike the earlier data-only battery change.
- **Gotcha.** Right after `containerapp update --image`, `az revision list` briefly showed BOTH the old and new revision active (single-revision mode still draining the old replica) → a metadata probe hit the old replica and returned `demo_flows: 0`. Resolved by itself once the old revision deactivated; **wait ~60 s after deploy before probing metadata**, or confirm the active revision image first. Re-probe confirmed 7 flows live on `oran-5g-ran`; telecom's 1 flow unaffected.

## 2026-06-21 — Sydney demo focus: O-RAN removed + narrative hardened for C-suite

- **Decision (user).** The synthetic narrative is what moves C-suite (open data never beats GridIQ, GridIQ never beats a test on their real data). Fabric/"Microsoft IQ" framing is intentional (Cosmos is a demo-affordability choice; engine swap is NOT reconciled in the story — C-suite doesn't care). Consolidate on the one Sydney fibre-cut story; **delete O-RAN**.
- **Removed.** `graph_data/data/scenarios/oran-5g-ran/` + `generate_oran_dataset.py` + `generate_oran_knowledge.py` (local). `graph_data/eval/` (generic harness) KEPT. Catalog now `demo-sandbox` + `telecom-playground-v2` only (verified live). Cosmos `oran` db + 4 `oran-*` search indexes LEFT in place (cost-only; destructive teardown deferred to explicit go-ahead).
- **Narrative audit (data ⊨ story).** Traced the fibre-cut end-to-end in the seeded graph: fault `LINK-SYD-MEL-FIBRE-01` → `MPLS-PATH-SYD-MEL-PRIMARY` down → ACME+BigBank primary down; their SECONDARY failover rides `FIBRE-02` which **shares `CONDUIT-SYD-MEL-INLAND`** with the primary (fake redundancy is REAL in data); truly diverse path = TERTIARY via Brisbane. OzMine ($40k GOLD) routes via SYD-BNE → **unaffected**. Blast radius = exactly ACME $50k + BigBank $25k = **$75,000/hr**. New guardrail `scripts/check_narrative_consistency.py` re-derives this from the CSVs and asserts it (→ `NARRATIVE_CONSISTENT`); run after any data edit.
- **Prompt hardening (live ≈ replay).** Orchestrator synthesis (`orchestrator/orchestrator_preamble.md`) restructured to mandate: explicit **$/hr SLA exposure** (summed, per-tenant), a **bounded-blast-radius exclusion** (name the high-value service NOT affected), and an elevated **"The Non-Obvious Finding"** section (the shared-conduit reveal). `investigation_protocol.md` step-1 + `network_investigator_identity.md` now require the investigator to compute per-service SLA $ and run a physical-diversity (shared-conduit) check. Replay tour opening hook (`ui/replay_tour.yaml`, EN) rewritten stakes-first.
- **Verify.** Baseline orchestrator scored 3/5 narrative beats (missed the explicit $ number + the OzMine exclusion; the shared-conduit insight + act-leg were already strong). After deploy (`pathfinderiq:20260621-syd-narrative`): **5/5 live** — states `$75,000/hour = ACME GOLD $50k + BigBank SILVER $25k`, excludes OzMine GOLD $40k as unaffected, headlines the fake-redundancy finding, reroutes via Brisbane, dispatches to Goulburn GPS with OTDR. ~277 s, full act-leg.
- **Next polish (deferred).** The scripted `ui/replay_conversation.json` (+ JA/ZH replay variants) still carries the PRE-hardening synthesis — re-record from the improved live orchestrator so scripted ≈ live; a visual blast-radius highlight on the topology graph is the highest-value remaining demo upgrade.

## 2026-06-21 — Sydney demo: scripted-replay aligned to live + graph "Incident Focus" blast-radius highlight

- **(1) Replay ≈ live.** The scripted replay (`ui/replay_conversation.json`, generated by `app/frontend/scripts/patch_replay_conversation.py`) already carried the shared-conduit insight + `$50k+$25k=$75k` breakdown; gaps vs the hardened live orchestrator were the **OzMine bounded-blast-radius exclusion** and naming the **truly-diverse Brisbane path**. Surgically patched the EN orchestrator final synthesis to add both (robust JSON edit, asserts substrings, revalidates). Deployed `…-syd-replay`. (JA/ZH replay variants still pre-patch — EN is the CIO demo; deferred.)
- **(2) Graph blast-radius highlight.** New **"◎ Incident Focus"** toggle in the graph header (`GraphHeaderBar`) that emphasises the fibre-cut blast radius (amber halo on the 14 incident nodes, everything else dimmed + non-incident links faded) and switches to the force-graph view. Driven by an `_incident:"true"` property added to the relevant nodes in the pack's `topology.json` (the cut + fake-backup FIBRE-02 + endpoints + ACME/BigBank + their SLAs + the shared conduit + the 3 MPLS paths + Goulburn amp/depot). **OzMine deliberately NOT flagged** → stays dimmed, visually reinforcing "not affected".
  - **Safety property:** the toggle **defaults OFF** and `incidentFocus` empty/false = byte-identical render → zero change to the default view for every scenario; the button only appears when the topology has `_incident` nodes (`hasIncident`). Files: `topology.json` (data), `GraphCanvas.tsx` (paint), `GraphTopologyViewer.tsx` (state+toggle+view-switch), `GraphHeaderBar.tsx` (button). No backend/store wiring — the graph reads `properties._incident` natively.
- **Verify.** `tsc --noEmit` clean + `npm run build` green. **Visually verified in the integrated browser** against the local no-auth render harness (backend `AUTH_ENABLED=false LLM_PROVIDER=echo` + vite): the `◎ Incident Focus` button renders (hasIncident detected the 14 flags), clicking it activates + switches to Graph view, and the canvas shows the amber emphasis. Deployed `…-syd-graph`; live topology serves 14 `_incident` nodes (first probes hit the draining old replica → 0, then 14 — the documented revision-drain gotcha; wait ~60 s post-deploy).
- **Next polish (deferred).** Extend the highlight to the default **map** view (currently force-graph only; the toggle switches view); re-translate the JA/ZH scripted replays to the patched EN synthesis; optional auto-enable Incident Focus during replay.

## 2026-06-21 — Graph view UX overhaul (the force-graph was an unreadable white blob)

- **Reported (user, via live look):** nav bar cluttered/clipping, pure-white graph background hard to read, node labels tiny+faded, nodes piled on top of each other. Confirmed by screenshotting the local no-auth render harness in the integrated browser — the force view rendered ~90 nodes as one illegible central blob on white with overlapping labels.
- **Root cause of the blob (the real bug):** `GraphTopologyViewer` passed **new `filteredNodes`/`filteredEdges` array refs every render** → react-force-graph re-initialised the whole layout each render, discarding positions + any force tuning → permanent collapse. Fixed by **memoising** the filtered arrays (`useMemo` keyed on data + active filters) so node identity (and x/y) persists.
- **Fixes (`GraphCanvas.tsx`):** dark canvas background `#0e1726` (was transparent→white); stronger spacing forces applied after engine init + re-applied over ~2 s (`d3Force('charge').strength(-550)`, link `distance(120)`/`strength(0.2)`, `d3VelocityDecay 0.25`) + `onEngineStop → zoomToFit` to frame the settled layout; **labels-on-zoom** (node labels only when `globalScale > 1.4` or incident-focused; edge labels only `> 1.7`) so ~90+111 labels stop smearing — hover tooltip still shows names; bigger/bolder light labels (`600 …`, `#E5E7EB`), lighter node borders + links.
- **Nav (`GraphHeaderBar.tsx`):** flipped the view toggle to show the **target** view (`🗺️ Map` in graph view) instead of duplicating the panel title; header `overflow-x-auto` so controls scroll instead of clipping.
- **Result (browser-verified):** clean, spread, dark network topology with legible structure; no label smear; nav reads correctly. `tsc` + `npm run build` green. Deployed `pathfinderiq:20260621-graph-ui`. Note: default view is still the cream "Map"; the dark force view + Incident Focus is the toggle. Deferred: optional map-view background polish; making graph the default view.

## 2026-06-21 — Cream Map view readability pass (default view, kept as paper atlas)

- **Brief:** keep the cream "Map" as the default view but make it massively more readable/clear for the CIO demo. Map = decorative road-atlas re-skin of the same react-force-graph engine (`MapCanvas.tsx` + `mapRendering.ts`).
- **Node spacing (`MapCanvas.tsx`):** map had NO force tuning → towns packed centrally. Added the same retry-over-2s force effect as the graph view (`d3Force('charge').strength(-620)`, link `distance(130)`/`strength(0.18)`, `d3VelocityDecay 0.28`) + `onEngineStop → zoomToFit(500,60)` to frame the settled atlas.
- **Label declutter:** `drawTownMarker` callouts were always-on (`globalScale ≥ 0.12`) → 90 overlapping boxes. Now `showLabel = globalScale > 1.2 || emphasize` (incident towns always labelled); road codes only at `globalScale > 1.4` or on incident roads. Hover tooltip still shows every name.
- **Incident Focus now works on the map** (was force-graph only; toggle no longer yanks you to the dark view — `handleToggleIncidentFocus` keeps the current view). Incident towns get an amber ring + halo + always-on callout; incident roads get an amber underglow; everything else dims (`globalAlpha 0.32` nodes / `0.18` roads). `incidentFocus` prop threaded GraphTopologyViewer → MapCanvas → `drawTownMarker(opts)` / `drawRoad(emphasize)`.
- **Noise reduction (`mapRendering.ts`):** the busy layers competed with topology. City-tile texture now drawn over a solid paper base at `globalAlpha 0.4` (was full strength); parks `18%→8%` of nodes + scattered `14→6`; rivers `3-5→2-3`; lakes `3-5→2-3`. Paper feel kept, clutter cut.
- **Repaint nudge (both canvases):** the render loop parks once the layout cools, so toggling Incident Focus while paused did NOT redraw until the next pan/zoom. Added `useEffect([incidentFocus, frozen])` that `resumeAnimation()` then re-`pauseAnimation()` after 700ms → emphasis/dimming now appears instantly on toggle. Applied to `GraphCanvas.tsx` too (same latent gap in the already-shipped graph incident focus).
- **Verified (browser, local no-auth harness via vite + a stub :9000 serving the real topology.json):** cream map renders spread + decluttered; Incident Focus instantly rings the 14 blast-radius towns (LINK-SYD-MEL-FIBRE-01, MPLS paths, VPN/SLA ACME+BigBank, CONDUIT-SYD-MEL-INLAND, AMP/DEPOT-GOULBURN) and dims the rest; legend/compass/banner intact. `tsc` + `npm run build` green. Deployed `pathfinderiq:20260621-182647-mapread`.
- **Landmine:** react-force-graph stops its RAF render loop on engine cooldown — any prop that only affects the canvas paint callbacks (not graphData/layout) needs an explicit repaint nudge or it silently no-ops until interaction.

## 2026-06-21 — Map pan/zoom regression (auto-fit hijacked navigation)

- **Reported:** map drag/zoom navigation borked.
- **Cause:** the readability pass added `onEngineStop={() => zoomToFit(...)}` to both `MapCanvas` and `GraphCanvas`. `onEngineStop` fires every time the simulation cools — including after a node drag or any interaction-triggered reheat — so the viewport snapped back to fit on every settle, making pan/zoom feel broken.
- **Fix:** one-shot `hasFitRef` guard. Auto-fit (onEngineStop + the timed fallback, pushed out to 3.5 s) frames the layout exactly once per `dataVersion`, then never re-fits. User pan/zoom now persists. Verified locally: synthetic wheel-zoom raised the canvas transform `a 0.20→0.31` and it held through a 2.5 s settle with no snap-back. Deployed `pathfinderiq:20260621-183808-mapnav`.
- **Landmine:** never call `zoomToFit` from `onEngineStop` unconditionally — the engine re-cools after every drag/reheat. Guard it to fire once, or the view fights the user.

## 2026-06-21 — Capability beats: operator approval + Work IQ + dollars-saved (C-suite clarity)

Surfaced built-but-dormant capabilities as three new demo beats, optimised for a C-level telco audience (no engineer-tool noise). All browser-verified in the local replay, deployed `pathfinderiq:20260621-202736-capabilities`.

- **Operator-approves-dispatch (`present_options` / OptionsCard):** the orchestrator now presents a clean, costed choice — *one engineer to Goulburn (recommended)* vs *two teams* — before any field dispatch. Component already existed but was never triggered; wired into the scripted replay (orchestrator thread, before `dispatch_field_engineer`) + `present_options` added to the orchestrator tool list + preamble instruction "operator approval before dispatch."
- **Work IQ pillar (`ask_work_iq`):** the comms specialist first queries Microsoft 365 (spoofed) for customer escalation contacts (Priya Naidoo/ACME, Tom Webster/BigBank), ACME's contractual **15-minute** notification clock, and the Teams governance note that the shared-conduit risk was already known. New **WorkIqResult** renderer (clean "Work IQ · source" card, markdown body — no raw JSON); `ask_work_iq` added to comms tool list + identity prompt + a `people-customer-contacts` catalog entry for live runs.
- **SLA dollars-saved + adaptive severity:** orchestrator synthesis now states the **financial outcome** ("reroute in ~90s → exposure held to ≈$1,900 vs $75,000/hr") and the **severity rationale** ("$75k/hr + multi-service blast radius ⇒ SEV-1"). Added to the scripted synthesis + the live preamble synthesis structure (new sections 6/7).
- **Edited:** `ui/replay_conversation.json` (via idempotent `app/frontend/scripts/enhance_replay_csuite.py`), `ui/replay_highlights.yaml` (+2 captions), `ui/replay_tour.yaml` (Remediation + Comms beats; de-duplicated the Work IQ pillar label off Field Coordinator → Fabric IQ), `scenario.yaml` (tool wiring), orchestrator/comms prompts, tool-renderers registry, public replay fallback synced.
- **Deliberately omitted:** `find_capabilities` raw render — capability-search JSON reads as plumbing to a CIO. Kept the tool wired but out of the scripted beats.
- **Landmine:** the active replay is the scenario `ui/replay_conversation.json` (served via `scenario.replay_conversation_url`); the legacy `app/frontend/scripts/patch_replay_conversation.py` writes back to its OWN source (`public/replay-conversation.json`) and is NOT re-runnable. New replay edits go through an idempotent script against the scenario file (marker-guarded), and the public file is a synced fallback only. The local no-auth stub doesn't serve scenario tour/replay assets, so tour overlays show bundled fallbacks locally — the deployed image serves the edited scenario assets.

## 2026-06-21 — Narration de-jargon + flat operational map (deployed `…-clarity`)

- **De-jargoned the audience-facing narration** (CIO glaze guard): both tour files (`ui/replay_tour.yaml` + `replay_tour_detailed.yaml`) NI beat dropped "GQL / Fabric Eventhouse (KQL) / network ontology / per-sensor fault localization" → plain "live network graph / real-time optical telemetry / pinpoint the fault." Same in the agent product summaries + `powered_by` labels in `scenario.yaml` (Fabric IQ kept as the brand; the `(GQL + KQL)` qualifiers removed) and the `AgentTabBar.tsx` hardcoded fallbacks. **Left the agent PROMPTS untouched** — they legitimately need GQL/KQL to drive the live queries; only the audience copy changed.
- **Rewrote the "Investigation Complete" close** (both tours) to bank the new capability wins: human-approved dispatch, reroute-in-90s → exposure held under $2,000, and right-customers-notified inside the 15-minute window via Microsoft 365.
- **Map: flat "Fill Corners" is now the default** (`MapCanvas` `flat` initial state `true`; fit padding `flat?14:60`). Cleaner operations-console layout, no 3D paper tilt on load (toggle still available).
- **Map made more operational without losing warmth:** removed the parallax clouds (`drawClouds` call + import), thinned decorations (near-node parks 8%→4%, scattered 6→3, rivers 2-3→1-2, lakes 2-3→1-2), softened the city-tile base (alpha 0.4→0.3). Kept the cream paper + Legend + compass so it stays friendly. Browser-verified: clean flat topology, clear road hierarchy, legend/compass intact.
- Note: feature name labels (parks/lakes) render at ~7px world units → effectively invisible at the default fit zoom, so no removal needed (and avoids `noUnusedLocals` churn on the label-colour consts).

## 2026-06-21 — Production-bundle graph crash + Clarity CSP (deployed `…-bugfix`)

- **Graph crashed in production only:** `Uncaught ReferenceError: Cannot access 'Rn' before initialization` in `graph-DLadSj9v.js`. Root cause: the Vite `manualChunks` rule force-combined `react-force-graph` + `force-graph` + `/d3` into a single `graph` chunk, which created an **intra-chunk circular-init TDZ** that only manifests in the minified production bundle. Fix: return `undefined` for those libs in `manualChunks` so Rollup orders their init naturally (folds into the entry; +~30 KB gzip — acceptable). `vite.config.ts`.
- **LANDMINE (critical verification gap):** `npm run dev` (vite dev server) does NOT reproduce production chunk-splitting, so every prior browser verification in this session passed while the **deployed graph was crashing**. ALWAYS verify UI/graph changes against a **production preview** (`npm run build && npm run preview`, port 4173) before declaring done. Added a `preview.proxy` block to `vite.config.ts` so the prod preview can reach the `:9000` stub. Reproduced the exact `graph-DLadSj9v.js` TDZ in preview, fixed it, confirmed the canvas renders.
- **Clarity CSP:** the Microsoft Clarity loader (`www.clarity.ms/tag/...`) pulls a second script from `scripts.clarity.ms`, which the CSP `script-src https://www.clarity.ms` blocked. Broadened to `https://*.clarity.ms` in `script-src` + `connect-src` (`deploy/nginx.conf`). `frame-src 'self' + login.microsoftonline.com` preserved (regression R1).
- Verified the fix on the bundle-identical production preview (graph renders, no `Rn` error); the live app is behind Microsoft sign-in so post-login live verification needs operator creds. Tell users to hard-refresh (Ctrl+Shift+R) to bust the cached old `graph-*.js` chunk.

## 2026-06-21 — Auth 401: v1 vs v2 token issuer mismatch (deployed `…-authfix`)

- **Symptom:** `API 401: Issuer https://sts.windows.net/{tenant}/ does not match configured tenant {tenant}` — the tenant GUIDs are IDENTICAL, which is the tell: it's a **v1/v2 issuer-format mismatch**, not a tenant mismatch.
- **Root cause:** `app/backend/app/auth.py` only accepted the v2 issuer `https://login.microsoftonline.com/{tenant}/v2.0`. When the API app registration's `accessTokenAcceptedVersion` is null/1, Entra issues a **v1** access token whose `iss` is `https://sts.windows.net/{tenant}/` (trailing slash, no version). Two checks rejected it: `_validate_issuer` (single-tenant exact-string match) and Step 5b (signing-key issuer exact-string match).
- **Fix:** accept BOTH issuer formats. `_validate_issuer` single-tenant now matches an `accepted` set of `{login.microsoftonline.com/{t}/v2.0, sts.windows.net/{t}/}`; `_ISSUER_RE` (multi-tenant) now matches either format; Step 5b compares **tenant GUIDs** (`_tenant_from_issuer`) instead of the full issuer string, preserving tenant-pinning while being format-agnostic. Audience check already accepted both `client_id` and `api://client_id`.
- **Verified:** added `test_single_tenant_accepts_v1_issuer`; full `tests/unit/test_auth.py` green (32 passed). Live post-login verification needs operator creds (can't drive Entra sign-in headlessly) — unit test reproduces the exact rejected scenario.
- **Alternative (not taken):** flip the API app registration to `accessTokenAcceptedVersion: 2` so it issues v2 tokens. Code-side dual-accept is more robust (survives app-reg drift) and in-scope.

## 2026-06-21 — Flat-map pan/zoom broken (BCR patch ran in flat mode) (deployed `…-mapnavfix`)

- **Symptom (after the flat "Fill Corners" default shipped):** map drag/navigate unresponsive + extremely slow scroll + map "disappears when you navigate away."
- **Root cause:** `MapCanvas` patches `Element.getBoundingClientRect` on the paper/canvas/force-graph divs to undo CSS-**3D-transform** distortion (needed for the tilted-paper view). That patch ran **unconditionally**, including in the new flat (no-transform) default — where native BCR is exact. The patched rect (off by the 3px paper border, and a `MutationObserver` re-patching every force-graph DOM mutation) fed d3-zoom/drag wrong coordinates → sluggish/erratic pan-zoom and stale framing on remount.
- **Fix:** gate the BCR-patch `useEffect` on `!flat` (early-return when flat; deps `[flat]` so it restores native BCR + disconnects the observer when switching to flat). In flat mode the canvas now uses native, exact BCR and no observer overhead.
- **Verified (dev AND prod preview):** wheel-zoom responsive (1.79→2.94, proportional); canvas BCR distinct from its container (800 vs 794 = patch off, native layout); panel off→on re-fits + redraws (not blank); Map↔Graph view toggle keeps content. Deployed `pathfinderiq:20260621-220554-mapnavfix`.
- **Landmine:** a `getBoundingClientRect` override installed for a CSS-3D-transform view MUST be disabled when the transform is absent — otherwise it silently corrupts d3-zoom/drag pointer math. Tie such patches to the exact mode that needs them.

## 2026-06-21 — Graph blanks on panel resize while paused (deployed `…-resizefix`)

- **Symptom:** dragging the chat/graph splitter blanks the graph until you click play.
- **Root cause:** same paused-no-repaint class as the Incident Focus bug — resizing changes the canvas `width`/`height`, but when the simulation is paused the render loop is parked, so the resized canvas never repaints (blank) until "play" resumes it.
- **Fix:** added a `useEffect([width, height, frozen])` to both `MapCanvas` and `GraphCanvas` that `resumeAnimation()` on size change then re-`pauseAnimation()` after 400 ms — so the canvas redraws at the new size during/after a resize even while paused. Same proven nudge as the Incident Focus repaint.
- **Verified (production preview):** with the map paused, forcing the canvas `height` to change (528→228→264, via the node-filter-bar toolbar-height toggle — the harness can't drive the `useResizable` pointer drag) repainted every time (`paintedShow`/`paintedHide` true, never blank). Deployed `pathfinderiq:20260621-224057-resizefix`.
- **Note:** synthetic pointer/mouse events (even Playwright's real mouse) did not engage `useResizable`'s drag in the integrated-browser harness (canvas height never changed); verify resize-driven repaints via a control that changes the height prop (toolbar toggle) instead.

## 2026-06-21 — THE navigation root cause: `autoPauseRedraw` froze pan/zoom (deployed `…-navrepaint`)

- **Symptom:** "Incident Focus breaks navigation / non-responsive." Reproduced more generally: with the graph **paused**, pan/zoom updated the d3-zoom transform but the canvas **did not visually repaint** (pixel hash unchanged) — the view looked frozen. This is the true root cause behind the whole run of "map drag broken / slow / disappears" reports; earlier fixes addressed real adjacent bugs but I'd only ever measured the *transform* (which changes) not the *pixels* (which didn't).
- **Root cause:** react-force-graph's `autoPauseRedraw` defaults to `true`, which **skips canvas redraws when the layout engine is idle**. Our custom `nodeCanvasObject`/`linkCanvasObject` depend on the **zoom level** (labels-on-zoom, incident emphasis/dimming), so when idle+paused a pan/zoom changed the transform but react-force-graph never redrew → frozen navigation. `usePausableSimulation` freezes on mouse-**enter** (to stop tooltip jitter), so the engine is idle exactly while you navigate — guaranteeing the stale frame.
- **Fix:** `autoPauseRedraw={false}` on both `MapCanvas` and `GraphCanvas` ForceGraph2D → redraw every frame so pan/zoom always repaints. Also simplified the incident/resize repaint nudges to `resumeAnimation()`-only (removed `pauseAnimation()`, which hard-stops the render loop and *caused* the freeze when it ran after a toggle).
- **Verified (dev AND prod preview):** with the map paused, wheel-zoom now visually repaints (screenshot: zoomed-in labels render); with **Incident Focus ON + paused**, zoom repaints with amber rings + dimming visible. Deployed `pathfinderiq:20260621-230645-navrepaint`.
- **Landmine:** ANY react-force-graph view with zoom-dependent custom `nodeCanvasObject`/`linkCanvasObject` MUST set `autoPauseRedraw={false}`, or pan/zoom silently stops repainting once the engine idles. Verify navigation by hashing **canvas pixels**, never just `getTransform()` (the transform changes even when nothing repaints).

## 2026-06-21 — UI design pass (tool → product polish for the CIO demo)

Full P0–P2 sweep after a live UI assessment. All browser-verified, `tsc`+build green, deployed `pathfinderiq:20260621-194305-uidesign`.

- **Graph toolbar declutter (`GraphHeaderBar.tsx`):** 12+ controls collapsed to Map/Graph + Incident Focus + Fill Corners + counts + search; power/styling controls (Aa, 🎨, Nodes, Edges, pause, fit, refresh) moved behind a `⋯` overflow toggle (`showMore` flex/hidden wrapper; existing fixed-position popovers still anchor to their button refs).
- **Sidebar trim (`Header.tsx`):** merged Development + Service Health into one collapsed "Advanced" section (Service Health nested under a sub-label); compacted the heavy Fabric-capacity Note box into a single muted `ⓘ` line; brand H1 `2xl→xl` tracking-tight; product logos `h-9→h-7`.
- **Single accent (P1-4):** unified the stray emerald greens to brand teal `#117865` — the two sidebar replay CTAs and the map view-toggle now all use `brand` tokens. Road colors left semantic.
- **Map banner removed (`MapCanvas.tsx`/`mapRendering.ts`):** the in-canvas blue "Pathfinder IQ" banner duplicated the sidebar brand and overlapped the legend on narrow canvases — dropped the `drawMapBanner` call + import (function kept exported, unused).
- **Branded empty chat hero (`MessageList.tsx`):** rounded brand badge + value-prop tagline; primary action is now the filled-teal **Watch the Demo**, secondary outline **New Chat**.
- **First paint framed:** covered by the one-shot `hasFitRef` auto-fit guard from the nav fix.
- Verified in the local no-auth harness: toolbar shows `⋯` and the overflow reveals all hidden controls; sidebar shows SETTINGS/STYLES/LANGUAGE/ADVANCED/CONVERSATIONS with the compact note; map legend top-right with no banner overlap; teal accent throughout.

## 2026-06-22 — Gremlin `in` reserved-word fix + dev-sign side-channel enabled (deployed `20260622-gremlinfix`, rev `0000026`)

Investigation flow failed live with `GraphSyntaxException: Unexpected token: ')'`. Root cause = L16: Cosmos's Groovy Gremlin parser reserves `in`, so the network-investigator's bare anonymous `in('amplifies')` / `in('governs')` steps (inside `.by(...)`) were rejected, while `out(...)` worked.

- **Fix (`tools/_cosmos.py`):** central sanitizer `_sanitize_gremlin_reserved` (regex `(?<![\w.])in\s*\(` → `__.in(`) runs first in `_transform_gremlin`, so every LLM-emitted query is auto-corrected before guards/limit injection. Lookbehind preserves `within(` and top-level `.in(`; idempotent. Regression test `tests/unit/test_cosmos_guards.py::TestGremlinReservedWordSanitizer` (4 cases). Full `test_cosmos_guards.py` = 20 pass.
- **Dev-sign side-channel ENABLED:** set `DEV_PUBLIC_KEY_ED25519` (44 chars, padding intact — guarded against the GridIQ `IFS='='` truncation landmine; set via `az containerapp update --set-env-vars`, not the env-apply loop) → `install_signed_request_auth` mounts in `app/main.py`; verified middleware mounted (signed `GET /api/sessions` → 200, oid `devsign:probe`). Sign with `python -m agentkit.dev_tools.dev_sign request ...`; private key local-only at `~/.gridiq/dev_signing_key` (0600).
- **Live end-to-end verification (signed probe, rev `0000026`):** drove the SYD-MEL fibre-cut investigation through `orchestrator` → `networkInvestigator`. All 4 delegated tool results `status: complete`, **zero `GraphSyntaxException`, zero error envelopes**. The graph traversals returned the exact outputs of the two previously-failing queries: conduits (`CONDUIT-SYD-MEL-INLAND`), inline amplifiers (`AMP-SYD-MEL-GOULBURN`, `AMP-SYD-MEL-ALBURY`, the `in('amplifies')` leg) and governing SLAs (`SLA-ACME-GOLD`, `SLA-BIGBANK-SILVER`, the `in('governs')` leg).
- **Security note:** dev-sign is a public-verifier-only side-channel (no shared secret on the server); it stays mounted only while `DEV_PUBLIC_KEY_ED25519` is set. Unset it to fully restore Entra-only auth.

## 2026-06-22 — Agent hardening pass: regression bench + reserved-word generalization + dev-sign /events (deployed `20260622-agenthardening`, rev `0000027`)

Built on the now-enabled dev-sign side-channel to make agent behaviour repeatably provable.

- **#4 Regression bench (`scripts/regression_bench.py`):** dev-sign-driven live acceptance battery (lineage: GridIQ SB-DEV-BENCH). Per turn asserts: exactly one terminal `done`; zero error envelopes (`GraphSyntaxException`/`"error":true`/`failed`/`internal_error`); ≥ `min_tool_calls`; every `must_include` evidence token present (grounding, not hallucination); wall-clock under budget. Run: `PYTHONPATH=app/backend python3 scripts/regression_bench.py --base-url https://<fqdn>`. This is the gate before every deploy. Live: investigate 225s / graph_direct 17s, **2/2 PASS** on rev `0000027`.
- **#2 Reserved-word sanitizer generalized (`tools/_cosmos.py`):** `_GREMLIN_ANON_RESERVED_RE` now rewrites bare anonymous Groovy-reserved steps `in|and|or|not|is` → `__.<step>(` (was `in` only). Lookbehind `[\w.]` still preserves `within(`, `band(`, top-level `.in(`, `__.in(`. Prevents the whole reserved-word class deterministically (defense beyond the verified `in` bug). Prompt belt-and-suspenders: `query_language/gremlin.md` now instructs `__.` prefix for anonymous reserved steps. Tests: `test_cosmos_guards.py::TestGremlinReservedWordSanitizer` parametrized over all 5 words + embedded-identifier preservation (30 pass).
- **#1 Sub-agent tool calls verifiable headlessly:** the delegation broadcast channel `GET /api/sessions/{id}/events` already streams sub-agent tool calls (`query_graph`, `search_*`) to the UI (`useSessionEvents.ts` + `handleDelegationEvent`); it required a JWT and ignored the dev-sign principal. `sessions.py::session_events` now honours `request.scope["devauth_user"]` (mirrors the chat path) so headless probes + the bench can observe it. Live-proven: the bench `investigate` case subscribes to `/events` via dev-sign and asserts `query_graph` appears — PASS = dev-sign honoured on `/events` AND sub-agent graph traversal streamed. Ownership unchanged (isolation tests pass; principal oid `devsign:<slug>` must match the session's creating slug). Regression gate for this path = the live bench (ASGI-scope/middleware dependency makes it a live-only contract).
- **#3 Parallelize delegation — REJECTED by design.** Measured: investigate ~3 min, all 4 specialists delegated. But `orchestrator/investigation_protocol.md` mandates a **causal chain**: NetworkInvestigator → KnowledgeAnalyst (needs Step-1 diagnosis) → FieldCoordinator (needs Steps 1+2) → synthesize → CommunicationsSpecialist (needs synthesis). The delegations are dependent-by-design, not accidentally serial; parallelizing would break the protocol semantics and the "decompose → synthesize" narrative. Latency is structural to the 5-stage dependent chain. Legitimate latency levers (deferred, need a product call): trim orchestrator prompt context (10k tok), faster model, or a protocol redesign — none shippable without altering demo behaviour. The frontend replay copy ("delegates in parallel") is marketing for the pre-recorded tour, not the live protocol.
