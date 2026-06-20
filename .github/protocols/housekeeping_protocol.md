# Protocol: Autonomous Housekeeping Loop

A fully autonomous, time-unbounded protocol the **orchestrator** runs to drive the codebase to a robust, well-organized, extensible state that maximizes agent success. Survey → triage → execute → verify → document, looped until measurably clean or a hard stop. Every structural change is verified against the **Golden-Path Core-Flow Sweep** ([regression_protocol.md §0.5](regression_protocol.md)) — the codebase's safety net.

**Invocation.** Run autonomously when the user says: *"Run housekeeping"* / *"Clean up the codebase"* / *"Housekeeping loop"*. The orchestrator owns the loop end-to-end, dispatching `inquisitor`, `undertaker`, `bug_hunter`, `developer_vmagent`, `couturier` (the `ui/` frontend surface), and finally `documentation_curator`, consolidating findings, and gating each batch on the golden path (and, for `ui/` batches, the frontend net — §0).

**Prime directive.** The measure of success is **material structural improvement that makes future agent work easier, safer, and more directly executable** — not lines deleted, not churn. A clean codebase that still passes the golden path and is easier for the next agent to extend. Cosmetic edits that don't earn their regression risk are out of scope.

---

## 0. Invariants (hold for the entire loop)

These never relax, even mid-refactor:

- **Golden path is the gate.** No structural batch is accepted until `GOLDEN_PATH_PROBE_OK` is green after it (or, for non-shipping changes, the documented `doc-only no deploy` rationale from [regression_protocol.md](regression_protocol.md)).
- **Frontend batches carry their own net.** Any batch touching `ui/` is additionally gated by the frontend safety net before acceptance: `tsc --noEmit` + `vite build` green, Playwright e2e green, and `FRONTEND_AUTH_PROBE_OK` per [frontend_regression_protocol.md](frontend_regression_protocol.md) (CSP/auth path is UX-under-test — never stub `auth_enabled:false` or substitute dev-sign for login). The Python golden path alone does NOT cover the browser surface.
- **One change-class per batch, one owner agent, verify after each.** Never "refactor everything then test." Per-batch verification localizes any regression to one batch.
- **No parallel edits on shared files.** Backend choke points — `registry.py`, `config.py`, `engine.py`, `verify.py`, `state.py`, `contracts.py`, plus the newer `api/routers/{chat,sessions,workspace}.py`, `persistence/*`, and `models/stream.py`. Frontend choke points — `ui/src/components/chat/cards/registry.ts` (card dispatcher), `ui/src/stores/{chatStore,sessionStore,workspaceStore}.ts`, `ui/src/auth/*`, `vmagent/api/static.py` (CSP). Serialize anything touching them. Parallel is allowed ONLY for read-only survey and for edits on provably disjoint file sets.
- **Reachability before deletion.** `undertaker` must PROVE non-reachability before any removal. Dynamic `module:function` imports (tool loader manifest, skill manifests, source/materialization registries) are reachable even with zero static call sites. Grep-clean ≠ dead.
- **Fork discipline (spec §14) + env boundary + no new deps hold.** Housekeeping does not weaken `config.py`-only env reads, import from GridIQ, add a dependency (Python *or* `ui/` npm), or touch auth/CORS/dev-sign/CSP. If a clean-up wants any of these, it STOPS and asks.
- **Behaviour-preserving by default.** Structural moves go behind a stable interface; the public contract (CLI commands, API routes, tool names, MCP surface) does not change unless the user explicitly approved that finding in triage.
- **Stop-the-line on regression.** Any golden-path failure, unexpected error, or contract drift HALTS the loop. Fix-forward the offending batch (max 3 attempts) or revert it; never proceed on red.

---

## 1. Phase 0 — Baseline (lock the net)

Before any survey or edit:

1. Run the golden path: `python3 vm_agent/scripts/golden_path_probe.py VMAGENT_HOUSEKEEP_BASELINE_$(date -u +%Y%m%d_%H%M%S)`. **If it is not green, STOP** — never clean on a broken base; repair the core flow first under [regression_protocol.md](regression_protocol.md).
2. Capture baseline metrics (the improvement yardstick), write to `_snapshots/housekeep-baseline-<stamp>.json`:
   - file count, total LOC, per-module LOC (flag modules > 600 lines) — **Python `vmagent/` and TypeScript `ui/src/` both**;
   - test count + pass count (pytest **and** Playwright e2e + vitest);
   - duplication census (e.g. count of hand-rolled `_request(` HTTP/auth blocks across `tools/`; on the frontend, repeated fetch/auth-header blocks outside `ui/src/api/*`);
   - package-map accuracy (does `vmagent/README.md` match the real tree?);
   - `ui/` bundle shape (entry chunk size, lazy chunks — Monaco must stay code-split, not in the entry chunk);
   - dead-candidate count (symbols/modules/components with zero static references, pre-reachability-proof).
3. Record the current live image sha + revision so the loop's deploys are diffable against a known-good start.

---

## 2. Phase 1 — Survey (read-only, parallel-safe)

Dispatch in parallel (no edits → no collision). Each returns a findings list of `path + line + fact`, never edits:

| Agent | Mandate | Output |
| --- | --- | --- |
| `inquisitor` | Structural: module boundaries, package shape, duplicated control flow, layering violations, wrong/missing abstractions, god-modules. Where does the package map drift from reality? | structural findings + severity |
| `undertaker` | Dead-code census: unused symbols, orphan modules, retired probes, stale config, unreachable branches. **Candidates only — reachability proven in Phase 3.** | dead-candidate list + reachability evidence plan |
| `bug_hunter` | Fragility: silent failures, unbounded paths, validation gaps, brittle error handling on the now-larger surface. | defect/fragility findings + severity |
| `couturier` | `ui/` structural: component/store boundaries, duplicated fetch/auth blocks outside `ui/src/api/*`, dead components, card-registry shape drift, bundle bloat (Monaco must stay lazy), a11y/focus regressions on the IDE panes. | frontend findings + severity |

Scope hint to all: the DAA core (`engine/verify/contracts/materialize/state`) is young, load-bearing, and golden-path-proven — **flag egregious issues but treat structural churn there as high-risk** (Phase 2 decides). The `scripts/` directory (operator probes vs runtime deps), the per-adapter `_request()` duplication, and the `vmagent/README.md` package-map drift are known high-value backend targets. On the frontend, the card registry (`ui/src/components/chat/cards/`), the three Zustand stores, and the auth/CSP path are load-bearing — the auth/CSP surface is treat-as-RED (it broke real login once; see AUTODEV).

---

## 3. Phase 2 — Consolidate + Triage (orchestrator owns; gated)

The orchestrator reads all surveys and produces a single **Housekeeping Ledger** (`build_spec/housekeeping_<stamp>.md`):

```
Finding | Source | Motive vector | Risk | Action | Owner | Batch | Status
```

- **Dedupe + collapse** overlapping findings; surface contradictions.
- **Classify by motive vector:** `shape` (boundaries/duplication/abstraction), `state` (durability/cleanup), `contract` (CLI/API/MCP/tool drift), `knowledge` (docs/comments), `safety` (validation/error paths).
- **Classify by risk tier:**
  - **GREEN (safe-now):** proven-dead code, duplication extraction behind a stable interface, mis-located modules, doc drift. Auto-eligible.
  - **AMBER (careful):** anything touching a choke-point file, public contract, or the DAA core. Individual golden-path run per batch; behaviour-preserving proof required.
  - **RED (gated on user):** anything that would change a public contract, weaken an invariant, add a dep, or restructure the DAA engine. **Does not execute without explicit user approval** — the loop records it as `deferred-pending-approval` and continues with GREEN/AMBER.
- **Order batches** so reduction precedes restructuring: dead-code removal first (shrinks surface), then duplication extraction, then relocation/boundary fixes. Dependencies and shared-file conflicts resolved here.

The triaged ledger is the loop's work queue. RED items are listed for the user but never auto-executed.

---

## 4. Phase 3 — Execute (the autonomous loop)

For each batch in the queue, in order:

```
LOOP per batch:
  1. Assign owner agent + scope (one change-class, disjoint files where possible).
     - undertaker: removal (after proving reachability live — list/grep + manifest/registry check + a probe if dynamic).
     - inquisitor -> developer_vmagent: structural move behind a stable interface.
     - bug_hunter -> developer_vmagent: harden a fragility (add the guard + a regression test).
  2. Local gate: py_compile; env-boundary; pytest affected + the full suite; validate_skills. **For `ui/` batches also:** `tsc --noEmit` + `vite build` + Playwright e2e green.
  3. If the batch ships runtime: deploy (one atomic step), --mode verify, poll healthz new image_sha.
  4. VERIFY: run the Golden-Path probe. **For `ui/` batches also run `FRONTEND_AUTH_PROBE_OK`** (frontend net, §0). Green => accept batch, mark ledger row done, record the new metric delta. Not green => fix-forward (<=3 attempts) or REVERT the batch; never proceed on red.
  5. Pay forward any new landmine to AUTODEV in the same batch.
  NEXT batch.
```

Loop discipline:
- **Batches are small and reversible.** A batch that can't be golden-path-verified in one cycle is too big — split it.
- **AMBER batches get their own golden-path run**, never share verification with another batch.
- **Choke-point files are edited strictly serially.**
- **Removal batches** require the `undertaker` reachability proof attached to the ledger row before the edit.

---

## 5. Phase 4 — Re-survey (prove it improved, not just changed)

After the queue drains:

1. Re-run `inquisitor` (read-only) against the new tree — and `couturier` if any `ui/` batch ran. Did the targeted findings actually close? Any new boundary issues introduced by the moves?
2. Re-capture the Phase-0 metrics. The loop SUCCEEDS only if metrics improved materially: duplication down, dead modules removed, no module regressed past the size threshold without reason, package map now accurate, test count >= baseline.
3. Full golden path + the affected [regression_protocol §5](regression_protocol.md) deep-matrix rows for any surface touched.
4. If the re-survey reveals a fresh high-value, low-risk finding, it may be appended to the queue and the loop re-enters Phase 3 for it — **bounded by the termination conditions in §7.**

---

## 6. Phase 5 — Documentation reconciliation (`documentation_curator`, last)

Runs ONCE, after the structure is final (docs describe the final shape, not a moving target):

- Reconcile `vmagent/README.md` package map to the real tree (it has drifted before).
- Update `build_spec/CURRENT_STATE.md` rows for any moved/renamed/removed capability.
- Update `AUTODEV.md` (date + any new landmines from the loop).
- Update `VM_AGENT_SPEC.md` only if a structural decision changed an authority statement.
- Prune stale comments/docstrings on touched modules; do not add docs to untouched code.
- Fork Lineage register: no change unless a GridIQ-copied pattern moved.

---

## 7. Termination conditions (how the autonomous loop ends)

The loop is time-unbounded but NOT condition-unbounded. It terminates when ANY holds:

- **CLEAN (success):** the triaged GREEN+AMBER queue is drained, Phase-4 re-survey confirms metrics improved and no new high-value finding remains, golden path green, docs reconciled. Emit the success report (§8).
- **CONVERGED:** a Phase-4 re-survey produces no new GREEN/AMBER finding above a triviality threshold — the codebase is as clean as this pass can make it. Stop; list any remaining RED items for the user.
- **BLOCKED:** a batch fails the golden path and cannot be fixed-forward in 3 attempts and cannot be cleanly reverted — STOP, report the structural blocker, leave the tree on the last green state.
- **GATED:** only RED (user-approval) items remain — STOP, present them, do not auto-execute.

Hard stops (immediate halt, any phase): golden-path regression that won't revert; an edit that would weaken auth/CORS/env-boundary/fork-discipline/CSP; a proposed new dependency (Python or npm); contract drift not approved in triage.

---

## 8. Sign-off

Final report (one table + the ledger):

| Metric | Baseline | Final | Delta |
| --- | --- | --- | --- |
| total LOC | | | |
| modules > 600 LOC | | | |
| duplicated `_request` blocks | | | |
| dead modules/symbols removed | | | |
| tests (count / pass) | | | |
| package-map accuracy | | | |
| ui entry-chunk / Monaco lazy | | | |
| golden-path | green | green | held |
| frontend net (if ui touched) | green | green | held |

Completion line:
```text
housekeeping COMPLETE -- baseline <img/rev>, final <img/rev>, batches <n done/n total>, golden-path held all <n> runs, RED deferred <n>, wall <Xh>
```

Plus: the consolidated Housekeeping Ledger path, the list of RED items deferred for user decision, and any AUTODEV entries added. Never declare COMPLETE without: every accepted batch golden-path-verified, the Phase-4 metric-improvement proof, and the documentation_curator reconciliation.

---

## 9. Why this is safe to run autonomously

- **The golden path bounds every batch** — a regression is caught at the batch that caused it, not 10 batches later.
- **RED items can't auto-execute** — anything that could change behaviour or weaken an invariant waits for the user.
- **Reachability proof gates deletion** — dynamic imports can't be silently removed.
- **Termination conditions are explicit** — the loop converges and stops; it does not churn forever.
- **The tree is always left on a green state** — a blocked batch reverts, never half-lands.

This turns "clean up the codebase" from an unbounded, risky mandate into a verifiable, self-terminating loop whose every step is proven against the live core flow.
