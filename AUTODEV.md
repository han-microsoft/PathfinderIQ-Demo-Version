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
