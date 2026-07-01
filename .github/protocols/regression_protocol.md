# VM-agent Regression Protocol

Implement -> local gate -> deploy -> live regression -> observe -> fix-forward. Run this after any VM-agent change that affects shipped code, runtime config, cloud tools, auth, terminal, task/session behavior, MCP, GHCP, or DAA workflow contracts.

**Callable as a single command.** Run autonomously when the user says: *"Run regression on \<change\>"* / *"Standard regression"* / *"Full deploy + verify"* / *"Does this break the core flow?"*. The Core-Flow Sweep (§0.5) is the default confidence check for ANY change. The deep capability matrix (§4–§5) runs when the change touches a specific surface or on demand. Any change a human reaches through the chat / IDE surface ALSO runs the Human-POV acceptance lane (§0.7).

---

## 0.5 Core-Flow Sweep — the standardized confidence check (run for EVERY change)

The single sweep that proves a change did not break the compiler. It drives the **entire golden path on synthetic data** — create -> discover -> adapt -> plan -> confirm -> materialize -> verify -> publish -> render -> consume -> **expose API contract** -> cleanup — as a chain of atomic typed-tool calls, each gated on the prior. If this passes, the core flow is intact. 100% synthetic, guarded `vmagent_demo_*` only, 0 real-data mutations.

**Inspiration:** GridIQ's `regression_loop.md` — one callable command, one atomic call per item (never a single bash loop that hides which item regressed), a pass/fail table, and a fix-forward loop. Adapted here from "investigations/detectors/audits" to "the data-asset compiler chain."

### 0.5.1 Invocation

```bash
cd /home/hanchoong/CURRENT270425/gridiq_current_070526
set -a && source vm_agent/.env && set +a
az account set --subscription "$AZURE_SUBSCRIPTION_ID" -o none
export VMAGENT_GOLDEN_NONCE="VMAGENT_GOLDEN_$(date -u +%Y%m%d_%H%M%S)"
# after deploy + healthz confirms the new image_sha (AUTODEV 0.x.DD rollout-lag):
python3 vm_agent/scripts/golden_path_probe.py "$VMAGENT_GOLDEN_NONCE"
```

`scripts/golden_path_probe.py` composes the per-stage probes and drives the chain over signed `/api/exec`. It prints one digest line per stage and `GOLDEN_PATH_PROBE_OK <nonce>` only if all stages chain green AND the deliberate failure path publishes nothing and rolls back.

### 0.5.2 The chain — one atomic call per stage, each surfaces a one-line digest

| # | Stage | Tool(s) | Pass digest |
| --- | --- | --- | --- |
| 0 | Create synthetic data | engine generates deterministic nonce CSV | `synthetic sha=<…> rows=<n>` |
| 1 | Discover | `catalogue.scan` / `sources.discover` | `discover src_rows=<n> nonce_present=true` |
| 2 | Adapt (read) | `sources.read` + `sources.schema` (when source adapters live) | `adapt rows=<n> schema=<k cols>` |
| 3 | Plan | `workflows.plan` | `plan state=planned hash=<…>` |
| 4 | Confirm | engine single-use token | `confirm token_consumed=true` |
| 5 | Materialize | `workflows.run` -> `FabricEventhouseBackend` | `materialize table=<guarded> ids=<n>` |
| 6 | Verify (gate) | P6 checks | `verify passed=true checks=4` |
| 7 | Publish | P5 registry on durable Cosmos ledger | `publish asset_id=<…> kind=kql_db` |
| 8 | Render | `assets.render_consumption(snippet)` | `render kit_bytes=<n> has_location=true` |
| 9 | Blind consume | run KQL taken from the rendered kit, via `contract.location` only | `consume count=<expected>` |
| 10 | **Expose API contract** | `GET /api/tools`, `assets.find`, `profiles.list` (+ `sources.list` when live) | `api tools=<n> find_hit=true profile_gated=true` |
| F | **Failure gate** (the moat) | rerun stage 6 with an unreachable threshold | `gate state=verify_failed published=false rolled_back=true` |
| C | Cleanup | backend rollback | `cleanup deleted=<n> retained=0 real_touches=0` |

### 0.5.3 Pass criteria

- Stages 0–10 all green, chained (each gated on the prior).
- Stage 6 fires on the happy path (`passed=true`), and the **Failure gate (F)** proves a failing check **publishes nothing and rolls back** — the moat is the load-bearing assertion; a green chain without F is not a pass.
- Stage 10 proves every prior stage was reachable through the typed API a UI calls, and that profile/lens enforcement gates it.
- Cleanup: `retained=0`, `real_touches=0` (assert no write/delete targeted a non-`vmagent_demo_` name; no real blob/index/table read as a workflow source).
- Marker `GOLDEN_PATH_PROBE_OK <nonce>` printed.

### 0.5.4 When to escalate to the deep matrix

- Change touches a specific surface (auth, terminal, a cloud tool, MCP, a new adapter/lens) -> also run the relevant §4/§5 rows for that surface.
- Change adds a new extension unit (source adapter, drop-in tool, lens) -> add its create->discover->API-exposed row to §5 and include it in the chain.
- Pure docs/no-shipped-runtime -> `doc-only no deploy`, golden path skipped with that explicit rationale.

### 0.5.5 Sign-off

```text
vmagent_core_flow PASS -- image <sha>, revision <rev>, nonce <nonce>, golden 0-10+F+C green, retained 0, real_touches 0, wall <Xm>
```

Never declare core-flow PASS without the stage digests, the Failure-gate result, and the cleanup ledger.

---

## 0.6 Standard Data-Platform Eval — the named acceptance battery (run when data-platform surfaces change, or on demand)

The §0.5 Core-Flow Sweep proves the compiler on synthetic data. The **Standard Data-Platform Eval** proves the full 5-target battery end-to-end on REAL discovered data, both eval sets, and an independent second verifier — it is the named acceptance set defined in [data_pipeline_acceptance_protocol.md](data_pipeline_acceptance_protocol.md). Run it when a change touches discovery/adapters, materialization backends, the persistence/pipelines store, or the verifier app, and as the standard data-platform regression on demand.

**One callable entrypoint:**

```bash
cd /home/hanchoong/CURRENT270425/vm_agent
set -a && source .env && set +a
az account set --subscription "$AZURE_SUBSCRIPTION_ID" -o none
export VMAGENT_EXPECTED_IMAGE_SHA="<deployed image sha>"
export VMAGENT_VERIFIER_URL="https://vmagent-verifier.<env>.azurecontainerapps.io"
python3 scripts/eval/run_standard_eval.py "VMAGENT_X_$(date -u +%Y%m%d_%H%M%S)"
```

`run_standard_eval.py` composes the self-contained probes in dependency order — RG inventory → real discovery → EventHouse/Search/Ontology (both real+synthetic sets) → the Cosmos SQL + Gremlin **recorded blockers** → pipeline-persist → verifier dual-check — and prints one digest per step plus `STANDARD_EVAL_OK <nonce>` (or `STANDARD_EVAL_PARTIAL` listing genuine deviations). The 2 Cosmos blockers are EXPECTED doctrine (exact missing role recorded), not failures. Aggregated evidence: `_snapshots/standard-eval-<nonce>.json`.

Pass criteria: every feasible probe green, both recorded blockers blocked-as-expected, verifier green, existing data un-mutated (`real_touches=0`). See [data_pipeline_acceptance_protocol.md](data_pipeline_acceptance_protocol.md) for the full doctrine, hard rules, and the build-a-pipeline skill ([`build_data_pipeline`](../../skills/build_data_pipeline/SKILL.md)).

---

## 0.7 Human-POV acceptance — required for any OPERATOR-FACING change

A signed `*_OK` probe proves the **mechanism**; it does NOT prove a human can actually reach the capability with plain words. For any change a human reaches through the chat / IDE surface (a new skill/recipe/agent/tool an operator would invoke, a workflow, a UX flow), the change is NOT accepted on the signed probe alone — it must ALSO pass the **human-POV lane**:

- Drive the deployed app **as a human user**: ONE chat turn carrying the natural-language intent (the operator's words, not internal tool/skill ids), no direct tool invokes for the work.
- **PASS** = the intent is satisfied AND the trace shows the agent **discovered + assembled** the capability itself (search → instantiate/dispatch → execute) — not a hardcoded path.
- **FAIL signal** = the signed probe is green but the human-phrased request fails (works only when spoon-fed exact tool calls) — a product failure even though the mechanism passes.
- Procedure + the five layers it must satisfy: [capability_workflow_protocol.md](capability_workflow_protocol.md). Evidence: the human turn + tool trace + independent artifact check in `_snapshots/<capability>_e2e_<nonce>.json` (e.g. `DIAGNOSTIC_PREP_E2E_OK`).
- Internal-only changes (wire shapes, persistence, gating, refactors) are exempt — they need only §0.5 and the relevant signed probe.

This lane closes the gap between "the probe passes" and "a human asking in plain language succeeds." It is the standing requirement, not a per-feature option.

---

## Live-First Rule

- Local checks are pre-flight, not proof.
- PASS requires live proof on `pathfinderiq-aemo` whenever the changed capability can be deployed and probed safely.
- Docs/mockups may use local/browser proof only when they do not affect shipped runtime. The final report must say `doc/mockup-only no deploy` and name the proof performed.
- New runtime/API/tool/UI capability is not accepted from unit tests alone. It needs signed live API/browser proof, audit evidence, and cleanup/retention ledger.
- Each live proof is atomic and digestible. Do not hide capability failures inside one large bash loop.
- Expected external blockers count as `blocked_with_reason` only when the response is structured and the blocker is already documented.

## Scope

- Run from `/home/hanchoong/CURRENT270425/gridiq_current_070526` when deploying the canonical live app, or from this repository root for local-only doc/code hygiene.
- Write only under `vm_agent/`, `/tmp/`, `/sandbox`, guarded VM-agent Blob prefixes, guarded `vmagent_demo_` cloud resources, and VM-agent audit ledgers.
- Use live target `pathfinderiq-aemo`.
- Every created asset uses nonce `VMAGENT_REGRESSION_$(date -u +%Y%m%d_%H%M%S)`.
- Known external blockers must return structured blocked/access-denied results, not silent success.

## Ownership And Deletion Law

- Test-created means the resource, row, blob, file, run, or asset contains the current regression nonce in a server-controlled field, path, name, metadata tag, or audit record.
- Data sources not created by the current test are immutable. Regression may read, inspect, catalogue, and reference them. Regression must not delete, overwrite, rename, retag, truncate, reindex destructively, or otherwise mutate them.
- Data assets created by the current test are cleanup-required. If a safe delete exists, delete them before PASS. If no safe delete exists, record `retained_with_reason` with exact id/path/tag and cleanup owner.
- Any cleanup tool must verify nonce ownership immediately before deletion. Missing nonce evidence means delete is refused.
- Nonce ownership is transitive only through recorded run evidence. A source connected to a test-created flow is not test-created.
- Any attempt to modify or delete a non-test-created data source is a stop-the-line failure.

## 0. Pre-flight

1. `cd /home/hanchoong/CURRENT270425/gridiq_current_070526`.
2. Read `vm_agent/AUTODEV.md` if deploy or cloud behavior is involved.
3. Source config and pin subscription:
   ```bash
   set -a && source vm_agent/.env && set +a
   az account set --subscription "$AZURE_SUBSCRIPTION_ID"
   ```
4. Confirm target and nonce:
   ```bash
   export VMAGENT_TARGET=pathfinderiq-aemo
   export VMAGENT_REGRESSION_NONCE="VMAGENT_REGRESSION_$(date -u +%Y%m%d_%H%M%S)"
   ```

## 1. Implement

- Edit only files required for the change.
- Stay inside `vm_agent/`.
- One atomic concept per change batch.
- No drive-by cleanup.
- No auth/CORS weakening, dependency additions, destructive cloud actions, or writes outside `vm_agent/` without explicit user approval.

## 2. Local Gate

Run cheapest affected checks first. For broad VM-agent Python changes:

```bash
python3 -m py_compile $(find vm_agent/vmagent -name '*.py' | sort)
PYTHONPATH=vm_agent pytest -q vm_agent/tests/test_cli_help.py
PYTHONPATH=vm_agent python3 vm_agent/scripts/validate_skills.py
```

Prove env boundary:

```bash
python3 - <<'PY'
from pathlib import Path
bad = []
for path in Path('vm_agent/vmagent').rglob('*.py'):
	text = path.read_text()
	if path.name != 'config.py' and ('os.environ.get' in text or 'os.getenv' in text):
		bad.append(str(path))
if bad:
	raise SystemExit('env reads outside config: ' + ', '.join(bad))
print('env-boundary ok')
PY
```

## 3. Deploy

Use one atomic terminal call per step. Do not combine deploy and verify.

Full deploy:

```bash
./vm_agent/deploy_vm_agent.sh --mode full --yes
```

Verify only after deploy completes:

```bash
./vm_agent/deploy_vm_agent.sh --mode verify --yes
```

If a long command backgrounds or output retrieval fails, inspect active `deploy_vm_agent`, `az acr build`, or `az containerapp update` processes and newest `vm_agent/_snapshots/` files before retrying.

## 4. Live Capability Regression

Run through signed requests and `vmagent` inside `/api/exec` where possible. Each numbered item is an atomic check or small check group with a clear digest.

| # | Capability | Required proof |
| --- | --- | --- |
| 1 | Health/auth | `GET /healthz` returns `ok=true` and active `image_sha`; unauth `GET /api/whoami` returns 401; signed `GET /api/whoami` returns 200 with `source=devsign`. |
| 2 | Terminal | Unauth WebSocket rejected; Ed25519 dev-sign WebSocket handshake opens and echoes shell output for automated regression; browser Entra bearer/subprotocol path remains accepted; max sessions, idle/lifetime, byte cap, and audit are enforced. |
| 3 | Shell exec | Signed `/api/exec` runs `id` as `uid=1001(agent)`; sandbox cwd works; large output truncates without container restart; invalid cwd outside `/sandbox` is rejected. |
| 4 | Workspace | Create nonce file under `/sandbox`, read it, tree it, delete it, and prove path traversal outside `/sandbox` is rejected. |
| 5 | CLI/session | `vmagent chat new`; remember/recall nonce; inspect history/state; delete only nonce-owned session directory if test owns it. |
| 6 | Model/resources | `vmagent model` returns configured deployment; `vmagent resources --json --max 3` returns resource group data. |
| 7 | Registry/skills | List tools, list/show skills, unknown tool returns stable structured error. |
| 8 | Confirmation gate | Every `risk=write` tool fails without confirmation and passes only with accepted confirmation when capability is otherwise available. This proves current basic write confirmation, not the future DAA plan-token FSM. |
| 9 | Target allowlist | Alternate Storage/Cosmos/Fabric targets return `target_not_allowed` or equivalent structured refusal. |
| 10 | Blob/Search | Upload temporary Markdown under allowlisted prefix, index/query it, delete temporary blob if delete tool exists; otherwise retain by nonce with reason. |
| 11 | Azure AI Search workflow | Run `azure_search.process_blob_to_search` with nonce; verify source blob, processed blob, index count, Search result, and audit event. |
| 12 | Cosmos SQL | Account probe/list/read/query pass; demo write returns success for owned demo resources or structured `cosmos_access_denied`. |
| 13 | Cosmos Gremlin | Key capability returns booleans and no key material; guarded DB/graph creation only; load/query may return structured private-network blocker until DNS/path exists. |
| 14 | Fabric Lakehouse | Ensure `vm_agent_tests` folder; write/read demo CSV; hash match; reject non-demo read/write path. |
| 15 | Fabric Eventhouse | Guarded demo roundtrip; query expected aggregate or structured Fabric/Kusto error with completed resource IDs. |
| 16 | Fabric Ontology | Create/show/list guarded ontology under `vm_agent_tests`; delete guarded ontology if created; non-demo delete rejected. |
| 17 | MCP stdio/HTTP | List tools, call read tool, prove write call requires confirmation. |
| 18 | GHCP registry MCP | Discover registry tools and run read-only query; write workflow requires confirmation. |
| 19 | Audit ledger | Every registry call appends bounded JSON; no key material appears in tool audit, stderr, or retained evidence. |

## 5. DAA Vertical-Slice + Extension-Surface Regression

The DAA primitives are LIVE (see CURRENT_STATE.md §6). These rows are the deep per-capability proofs behind the §0.5 Core-Flow Sweep; run the ones a change touches, and always run §0.5 end-to-end.

| Capability | Required proof |
| --- | --- |
| Durable state (X1) | Health/state probe shows durable Cosmos store reachable; write/read nonce row; restart-survival (rows persist across revision restart); write workflows refuse when durable state is unavailable. |
| Catalogue rows (P1) | `catalogue.scan` / `sources.discover` emit `source` rows; rerun dedupes by `content_sha`; projection reflects current rows. |
| Source adapters | `sources.list/discover/read/schema` return bounded structured data via the adapter (not ad-hoc); a new adapter is drop-in (registered, API-visible) without core registry edits. |
| Workflow engine (P3) | `workflows.list/plan/run`; unknown workflow structured error; engine drives plan->confirm->apply->verify->publish/rollback with a durable FSM trail by `run_id`. |
| Plan FSM | Plan hash stable; confirm consumes single-use token; replay/expired/superseded transitions rejected. |
| Materialize (P4) | Backend builds only nonce-owned guarded `vmagent_demo_*` resources; `MaterializationBackend` abstraction targeted (not hardcoded); apply persists progress + terminal state. |
| Verify (P6) | Core-owned check classes verify nonce/evidence independently from workflow self-report; failed check ⇒ `verify_failed` ⇒ no publish ⇒ rollback (the moat). |
| Publish + contract (P5) | `kind=*` contract on durable ledger; lineage cites source + plan_id; `assets.find/get` resolve it; blind consume via `contract.location` only. |
| Render consumption | `assets.render_consumption(snippet)` produces a runnable kit from the contract alone; unpublished asset ⇒ structured refusal. |
| Profile/lens enforcement | `profiles.list/show`; `invoke_tool` refuses out-of-profile tools with structured `tool_not_in_profile`, audited; a lens changes prompt/model/behaviour. |
| Tool loader | A drop-in tool under `toolsets/custom/` appears in `GET /api/tools` with no core registry edit; obeys profile enforcement + audit. |
| Rollback | Uses recorded IDs plus tags; records `rolled_back`, `rollback_partial`, or `retained_with_reason`. |
| Export | JSON/Markdown export generated with redaction policy and audit entry. |

## 6. Cleanup Rule

- Never delete or modify data sources unless they were created by the current regression nonce.
- Always delete data assets created by the current regression nonce when a safe delete exists.
- Delete sandbox files/directories created by the nonce.
- Delete Fabric ontology items created by the nonce through guarded delete tool.
- Delete other guarded demo resources only when a safe delete tool exists and the resource is nonce-owned.
- For cloud services without safe delete tools, use unique nonce resources and record retained IDs with reason.
- Final result must report `created`, `deleted`, `retained_with_reason`, and `blocked_with_reason`.

## 7. Observe

Final report format:

| phase | ok / total | blocked | retained | notes |
| --- | --- | --- | --- | --- |
| local gate | n/n | 0 | 0 | |
| deploy/verify | n/n | 0 | 0 | image/revision |
| **core-flow sweep (§0.5)** | golden 0-10+F+C | 0 | 0 | `GOLDEN_PATH_PROBE_OK` |
| **standard data-platform eval (§0.6)** | feasible n/n | 0 (all 5 targets feasible as of 2026-06-11) | 0 | `STANDARD_EVAL_OK` / `_PARTIAL` |
| substrate | n/n | n | n | |
| registry/tools | n/n | n | n | |
| cloud workflows | n/n | n | n | |
| audit/cleanup | n/n | n | n | |

Include active image SHA, revision, nonce, total wall-clock, failed checks, blocked checks, retained resources, and audit evidence path. For any change that ships runtime, the core-flow sweep row is mandatory — a green deep matrix without a green golden path is not a pass.

## 8. Fix-Forward Loop

- Any unexpected failure, HTTP 5xx, unstructured error, missing audit event, missing auth gate, leaked key material, wrong identity, or unsafe mutation stops the sweep.
- Fix forward, redeploy, rerun from local gate unless failure is explicitly isolated to a later live-only check.
- Maximum three iterations before reporting structural blocker.

## 9. Sign-off

Completion line:

```text
vmagent_regression PASS -- image <sha>, revision <rev>, nonce <nonce>, golden 0-10+F+C green, blocked <n expected>, retained <n>, wall <Xm>
```

Never declare PASS without the final report table, the §0.5 core-flow stage digests (or an explicit `doc-only no deploy` rationale), and the cleanup ledger.
