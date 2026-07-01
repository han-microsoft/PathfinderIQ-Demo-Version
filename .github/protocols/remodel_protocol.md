# Protocol: Remodel (Refactor-to-Strength)

Deliberate teardown. Rip a god module apart, re-cut a boundary, re-standardize an
interface — rebuild fundamentally stronger. Bold by design. Safe by gate.

Traces to PART 0 T10 (nothing sacred) + C4 (structure provisional, strength
permanent). A god module is low signal-per-token AND high decay rate — it breaks
both laws. Teardown is the cure, not a risk to defer.

Distinct from siblings:

- [hygiene.md](./hygiene.md) — small ranked cosmetic pass.
- [housekeeping_protocol.md](./housekeeping_protocol.md) — incremental, behaviour-preserving loop.
- **remodel** — deliberate strength-increasing restructure. Behaviour-preserving
  externally, transformed internally. The protocol that *celebrates* teardown.

**Invocation.** *"Remodel \<target\>"* / *"Tear down and rebuild \<module\>"* /
*"Break up this god script"*. Orchestrator owns it; `inquisitor` and `developer`
execute.

---

## 0. Invariant — boldness with a net

Courage and safety stop being opposed once the gate is trusted.

- The net is the **core-flow check** (PROJECT.md §5). It must be green BEFORE
  teardown starts. Never remodel on a red base.
- External contract (CLI, API, tool names, public types) is preserved unless the
  user explicitly approved changing it. Internals are free game.
- Rebuild proves **equivalent-or-better**: same external behaviour, measurably
  better legibility (smaller modules, fewer boundaries crossed, less duplication,
  named seams).
- One target per run. A remodel that can't be gated in one cycle is too big — cut it.

## 1. Justify the teardown

Name why the target violates the laws. Write to the findings directory (PROJECT.md §3):

```text
<findings-dir>/remodel_<YYYYMMDD>_<slug>.md
```

Required:

- Target + current shape (LOC, concerns owned, inbound/outbound edges).
- Law violation: signal-per-token cost, decay rate, duplication, leaked boundary.
- Target shape: the stronger structure + why it raises both laws.
- Falsifying signal: what would prove the rebuild is NOT better (regression,
  more edges, contract drift). Pre-declared.

No teardown without a named target shape. Demolition without a blueprint is debt.

## 2. Lock the net

1. Confirm core-flow green (PROJECT.md §5). If red, STOP — repair under [regression_protocol.md](./regression_protocol.md) first.
2. Capture the equivalence baseline: external contract surface (routes, CLI,
   tool names, public signatures) + the metrics the rebuild must beat.
3. Pin the current behaviour with characterization tests where the contract is
   thin — the rebuild must keep them green.

## 3. Tear down + rebuild behind the net

- `inquisitor` cuts the new boundaries; `developer` implements the move.
- Build the new structure behind the stable external interface.
- Prefer legibility that cannot lie (C5): new seams carry types/contracts, not
  prose promises.
- Delete the old shape only when the new one is proven (hand dead remains to
  `undertaker` if non-trivial).
- One atomic concept at a time inside the remodel; keep each step gate-able.

## 4. Prove equivalent-or-better

- Local gate (PROJECT.md §4) green.
- Core-flow check (PROJECT.md §5) green — same external behaviour.
- Characterization tests green — no contract drift.
- Metrics beat baseline: module size down (`agent_tooling/module_size.py`),
  boundaries crossed down, duplication down (`agent_tooling/dup_scan.py`), or a
  named seam now exists where none did. If no metric improved, the remodel FAILED
  its own justification — revert.
- Shipped behaviour change ⇒ deploy + live regression ([regression_protocol.md](./regression_protocol.md)).

## 5. Pay forward

- Update the package map (PROJECT.md §3) to the new shape.
- Update the capability ledger rows for moved/renamed surfaces.
- New landmine from the teardown ⇒ gotcha log (PROJECT.md §3).
- Run [iterative_context_evolution.md](./iterative_context_evolution.md) if the
  remodel changed enough structure that README/VISION drifted.

## 6. Sign-off

```text
remodel COMPLETE -- <target>, external contract held, core-flow green, metrics <before -> after>, <deploy/live or doc-only>, old shape removed
```

Never declare COMPLETE if: core-flow red, contract drifted unapproved, or no
metric improved (teardown that didn't strengthen is churn).

## Hard Rules

- Green net before teardown. Never remodel on red.
- External contract preserved unless user approved the change.
- Equivalent-or-better proven, not asserted. No metric gain = FAIL.
- One target per run. Gate-able steps only.
- Nothing sacred (T10) — but nothing torn down without a target shape and a net.
- Rollback is not a fix; fix forward or revert the whole remodel atomically.
