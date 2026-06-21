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
