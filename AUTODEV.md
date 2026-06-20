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
