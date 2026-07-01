# VM-agent Data-Pipeline Acceptance Protocol

The **standard data-platform acceptance doctrine**: discovery-first construction of queryable data instances from real Azure data, dual-verified, persisted as reinitializable state, with honestly-recorded RBAC/network blockers. This is the executable doctrine behind the Phase-X eval battery (`scripts/eval/run_standard_eval.py`) and the named data-platform acceptance set referenced by [regression_protocol.md](regression_protocol.md).

Composes three protocols (links, never duplicates):
- [evidence_protocol.md](evidence_protocol.md) — the 3 artefacts (Definition / Evidence plan / Test protocol), pre-declared thresholds, Test Data Hygiene.
- [regression_protocol.md](regression_protocol.md) — Live-First Rule, Ownership & Deletion Law, fix-forward loop.
- [data_workflow_acceptance_protocol.md](data_workflow_acceptance_protocol.md) — real-asset reference + synthetic-asset execution, blind-consume-via-contract, structured-blocker-is-first-class.

---

## 0. What this protocol proves

One operator prompt — *"discover the data in this project and stand up the queryable instances"* — drives the agent to: discover the real estate → process real data with custom scripts → for each target either **materialize a NEW nonce-owned queryable instance** (where the managed identity has create rights) or **record a blocker with the exact missing role** (where it does not) → verify each instance queryable via its API → confirm callability from a **second independent verifier app** → persist the whole pipeline (scripts + outputs + handles + session) as reinitializable state → clean up only nonce-owned creates. The same battery is the standard eval every agent run is judged against.

**What this is NOT:** it is not a single-workflow acceptance (that is [data_workflow_acceptance_protocol.md](data_workflow_acceptance_protocol.md)); it is not a synthetic-only golden path (that is the Core-Flow Sweep, [regression_protocol.md](regression_protocol.md) §0.5). This protocol is the multi-target, real-source-first, dual-verified, persisted battery.

---

## 1. The doctrine — the pipeline lifecycle (per target)

```
discover (real, read-only)  →  process (custom script in /sandbox via /api/exec)
   →  materialize NEW nonce-owned instance   |  record blocker (exact missing role)
   →  verify queryable via the instance API
   →  two eval sets: (A) real-source-derived  +  (B) synthetic
   →  independent dual-verification (second verifier app, same UAMI, signed)
   →  persist as reinitializable state (scripts + outputs + handles + session)
   →  cleanup (nonce-owned creates only; existing data immutable)
```

1. **Discovery is the PRIMARY entryway.** Every run starts from the real RG inventory (`resources.inventory`) and drills into each resource the MI can read (`sources.discover` / `sources.read` / `sources.schema`). Discovery is generalizable to any project/RG — the boundary is RBAC, not config. No target is preconfigured as the source; the agent picks real discovered datasets.
2. **Custom-script processing is the intermediate stage.** The agent writes a processing script to `/sandbox`, runs it via signed `/api/exec`, and captures its output as the intermediate artefact. Real source bytes are read, never written.
3. **Materialize-new where rights permit; record-blocker where they do not.** A target with MI create rights produces a NEW nonce-owned instance (named/tagged with the run nonce). A target without create rights (control-plane role missing, private-endpoint unreachable, no key path) is recorded as a structured blocker with the **exact missing role / network reason** — this is part of the eval record, never faked, never substituted with "discover-existing" to manufacture a pass.
4. **Verify queryable via the instance API.** Each materialized instance is queried through its own data-plane API (KQL, Search query, ontology query, SQL/Gremlin query) and must return the nonce-stamped rows before it counts.
5. **Two eval sets are REQUIRED per feasible target.** Set A derives lineage + row count from a discovered **real** source (immutable). Set B re-runs the standardized pipeline on deterministic **synthetic** data. Passing both proves the pipeline is shaped for real data AND reproducible cheaply.
6. **Independent dual-verification.** A SECOND container app (`vmagent-verifier`, same image, same UAMI, its own FQDN, signed dev-key) independently calls the same instance + agent APIs and confirms callability. Same UAMI ⇒ identical data rights ⇒ the verifier issues read/verify only; the recorded blockers reproduce identically (proof they are real, not flaky).
7. **Persist as reinitializable state.** The pipeline run (source manifest + the custom scripts + raw/intermediate outputs + materialized-instance handles + the session link) is saved as ONE bundle (`POST /api/pipelines/save`) and reconstructed byte-identical (`/restore`) after the workspace loses the scripts.
8. **Cleanup.** Only nonce-owned created instances are deleted (each delete re-verifies nonce ownership). Existing data is immutable and never touched; the cleanup ledger shows `real_touches=0`.

---

## 2. Hard rules (non-negotiable)

- **Existing data is read-only.** Discovery, sampling, hashing, and querying only. Any write/rename/retag/truncate/reindex/delete of a non-nonce-owned source is a stop-the-line FAIL (inherits [regression_protocol.md](regression_protocol.md) Ownership & Deletion Law).
- **Nonce-owned creates only.** Every materialized instance carries the run nonce in a server-controlled name/tag; cleanup deletes only those and re-verifies ownership immediately before deleting.
- **RBAC/network blockers are recorded honestly, never faked.** A blocked target emits a structured `status=blocked` result with the exact missing role / network reason. Silent success, an unstructured exception, or substituting discover-existing for a failed create is FAIL.
- **Both eval sets are required** for every feasible (materializable) target: real-source-derived (A) and synthetic (B).
- **Managed identity only.** No connection strings, account keys, SAS, or admin keys (the one pre-existing flag-gated Gremlin key path stays gated and never returns key material).
- **Independent checkability.** Every probe is dev-sign + nonce + `_snapshots/` artefact; the verifier app is a separate caller; each sub-probe is self-contained and re-runnable. No hidden state.
- **Live-first.** No target is accepted from unit tests alone; each needs the signed live instance probe + the verifier confirmation + the persisted-state proof.

---

## 3. The standard battery (the named acceptance set)

The battery is the 5 data-platform targets + the read-only foundations + persistence + dual-verification, run in dependency order by `scripts/eval/run_standard_eval.py`. The current live verdict (image `20260611-123645`):

| # | Step | Probe | Marker | Outcome |
| --- | --- | --- | --- | --- |
| 1 | RG inventory (task 3) | `resource_inventory_probe.py` | `RESOURCE_INVENTORY_PROBE_OK` | feasible |
| 2 | Real discovery (task 2) | `discovery_real_probe.py` | `DISCOVERY_REAL_PROBE_OK` | feasible |
| 3a | Fabric EventHouse | `eventhouse_instance_probe.py` | `EVENTHOUSE_INSTANCE_PROBE_OK` | feasible — sets A+B |
| 3b | AI Search index | `search_instance_probe.py` | `SEARCH_INSTANCE_PROBE_OK` | feasible — sets A+B |
| 3c | Fabric Ontology | `ontology_instance_probe.py` | `ONTOLOGY_INSTANCE_PROBE_OK` | feasible — sets A+B |
| 4a | Cosmos NoSQL | `cosmos_sql_instance_probe.py` | `COSMOS_SQL_INSTANCE_PROBE_OK` | feasible — sets A+B (unblocked 2026-06-11: DocumentDB Account Contributor grant + ARM control-plane DDL; existing DBs untouched) |
| 4b | Cosmos Gremlin | `gremlin_instance_probe.py` | `COSMOS_GREMLIN_INSTANCE_PROBE_OK` | feasible — sets A+B (unblocked 2026-06-11: Gremlin private endpoint in the container app's VNet; existing graphs untouched) |
| 5 | Reinitializable state | `pipeline_persist_probe.py` | `PIPELINE_PERSIST_PROBE_OK` | feasible |
| 6 | Independent dual-verify | `verifier_probe.py` (2nd app) | `VERIFIER_PROBE_OK` | feasible |

**As of 2026-06-11 all 5 targets (3a–4b) are feasible — no recorded blockers remain.** (cosmos_sql unblocked via DocumentDB Account Contributor + ARM control-plane DDL; cosmos_gremlin unblocked via a Gremlin private endpoint in the container app's VNet — see [AZURE_CONVENTIONS.md](../../AZURE_CONVENTIONS.md).)

### 3.1 Verdict

- `STANDARD_EVAL_OK <nonce>` — every feasible step green AND the verifier green.
- `STANDARD_EVAL_PARTIAL <nonce>` — a feasible step failed, an UNEXPECTED blocker surfaced, an expected blocker unexpectedly passed, or the verifier was partial/skipped.

---

## 4. Run it

```bash
cd /home/hanchoong/CURRENT270425/vm_agent
set -a && source .env && set +a
az account set --subscription "$AZURE_SUBSCRIPTION_ID" -o none
export VMAGENT_EXPECTED_IMAGE_SHA="<deployed image sha>"
export VMAGENT_VERIFIER_URL="https://vmagent-verifier.<env>.azurecontainerapps.io"
python3 scripts/eval/run_standard_eval.py "VMAGENT_X_$(date -u +%Y%m%d_%H%M%S)"
```

- `--source-sets real,synthetic` (default) runs both eval sets per feasible target; `--source-sets real` runs set A only.
- `--skip-verifier` drops step 6 when no standing verifier app is available (records the verifier as skipped → PARTIAL).
- `--only inventory,discovery` runs a name-prefixed subset (each sub-probe stays independently runnable on its own too).

Aggregated evidence: `_snapshots/standard-eval-<nonce>.json` (per-step marker, rc, outcome, and the path of every sub-probe's own snapshot).

---

## 5. Final report

| field | value |
| --- | --- |
| image SHA / revision | … |
| nonce | … |
| feasible ok / total | …/… |
| recorded blockers | none (all 5 targets feasible as of 2026-06-11) |
| blocker drift | 0 expected |
| verifier | ok / partial / skipped |
| marker | `STANDARD_EVAL_OK` / `STANDARD_EVAL_PARTIAL` |
| cleanup | nonce-owned creates deleted; real_touches=0 |

Completion line:

```text
vmagent_standard_eval PASS -- image <sha>, nonce <nonce>, feasible <n>/<n>, blockers none, verifier ok, real_touches 0
```

Never declare PASS without the per-step digest, the two recorded blockers with their exact missing role, the verifier result, and the cleanup ledger (`real_touches=0`).

---

## 6. How to build a new pipeline (the captured skill)

The agent-facing *how* — discover → write custom processing script → materialize/verify per target → persist → eval — is captured as a runtime-discoverable skill: [`build_data_pipeline`](../../skills/build_data_pipeline/SKILL.md) (surfaced via `list_skills()` / `GET /api/skills`). It extends [`dataprocessing_workflows`](../../skills/dataprocessing_workflows/SKILL.md) (single-workflow five-stage lifecycle) to the multi-target, dual-verified, persisted battery this protocol accepts.
