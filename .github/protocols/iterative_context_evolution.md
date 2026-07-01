# Protocol: Iterative Context Evolution

The codebase is a plant; the agentic context is the pot. As the code grows, the
pot must be re-shaped to fit it — or the plant roots into stale assumptions. This
protocol is the orchestrator's periodic re-potting: it re-grounds the three
living context documents, prunes redundancy, and evolves the agent/protocol
stable to fit *this* project as it is now.

Run it after a milestone, a structural shift, a cluster of merged work, or
whenever the docs/agents have drifted from reality.

**Invocation.** Run autonomously when the user says: *"Run iterative context
evolution"* / *"Re-pot the context"* / *"Evolve the docs and agents"* /
*"Update AUTODEV/README/VISION"*. The orchestrator owns the loop end-to-end.

---

## The three living documents

Every project carries exactly three living context docs, each with a **single,
non-overlapping responsibility**. They resolve from [../PROJECT.md](../PROJECT.md):

| Doc | PROJECT.md role | Owns (and ONLY this) | Answers |
| --- | --- | --- | --- |
| **AUTODEV.md** | gotcha log (§3) | Operational lore: deployment guidelines, live-validated landmines, gotchas, fork lineage, infra hazards. | "What will bite me when I deploy or touch infra?" |
| **README.md** | package map / navigational index (§3) | Current file structure + what each part does + how to run it. A navigational index, not a capability ledger. | "Where is X and how do I run it?" |
| **VISION.md** | ambition / north-star doc (§3) | The eventual goal + a living progress marker of where we stand on the path to it. | "What are we building toward, and how far are we?" |

Demarcation is the load-bearing rule. If a fact about *what bites you* leaks into
README, or a *file-structure* fact leaks into VISION, the pot is malformed.
Each doc names its responsibility at the top and points at the other two.

If a project has not yet created one of these three, this protocol **establishes**
it (using the project's real state), then keeps it current on every subsequent run.

> Naming: these are the canonical roles, not literal filenames. A project may name
> them `GOTCHAS.md` / `README.md` / `VISION.md` or anything else — PROJECT.md §3
> binds the role to the actual path. The capability ledger (PROJECT.md §3), if the
> project keeps one separate from VISION, remains the source-of-truth for
> per-capability detail; VISION holds the *narrative* progress marker that cites it.

---

## 0. Invariants

- **One responsibility per doc.** No capability detail in README; no file-structure
  in VISION; no roadmap in AUTODEV. Cross-link instead of duplicating.
- **Truth over aspiration.** Every claim reflects the code as it is now. Aspirational
  statements live in VISION's goal section, explicitly marked as not-yet-built.
- **Evidence-bound.** A landmine in AUTODEV cites the probe/commit that proved it.
  A "live" marker in VISION cites the evidence (PROJECT.md §5 pass signal, a probe,
  a test). No vibes.
- **Prune, don't hoard.** Redundant, superseded, or contradicted text is removed or
  archived (PROJECT.md §3), not left to rot. Smaller true docs beat large stale ones.
- **Agent/protocol evolution is in-scope** — strength-increasing teardown encouraged
  behind the gate (T10); the constitution ([../copilot-instructions.md](../copilot-instructions.md))
  and the universal principles do not get diluted to fit one project (see §4).
- **No invented facts.** If current state is unknown, dispatch a read-only survey
  (`Explore` / `documentation_curator`) before writing. Mark `unknown:` rather than guess.

---

## 1. Phase 0 — Survey current reality (read-only)

Before touching any doc, establish ground truth. Dispatch in parallel:

| Agent | Mandate | Output |
| --- | --- | --- |
| `Explore` | Real file tree + entry points + how-to-run, vs what README claims. | structure delta |
| `documentation_curator` | Drift/dup/bloat across the three docs; demarcation violations; broken links. | doc findings |
| `inquisitor` (optional) | Has the package shape changed since README's map was written? | boundary delta |

Also read directly:

- the three living docs (PROJECT.md §3 roles);
- the capability ledger (PROJECT.md §3) for per-capability truth;
- recent findings under the findings directory (PROJECT.md §3);
- the agent stable (`../agents/*.agent.md`) and protocols (`./*.md`).

Output a short reality map under the findings directory:

```text
<findings-dir>/context_evolution_<YYYYMMDD>.md
```

## 2. Phase 2 — Reconcile the three documents

Update each to its responsibility ONLY. One doc at a time (`documentation_curator`
owns the edits, or the orchestrator edits directly when the user requested it).

### AUTODEV.md (gotcha log)

- Add new deployment guidelines and gotchas discovered since last run, each with
  the proving probe/commit.
- Promote `(anticipated)` entries to confirmed when a probe validated them; drop
  predictions that proved false.
- Fold duplicate landmines into one canonical entry.
- Keep the newest, infra-touching, deploy-breaking hazards near the top.

### README.md (navigational index)

- Reconcile the file/structure map to the real tree (Phase-0 structure delta).
- Update "how to run / how to deploy" to the current commands (PROJECT.md §4).
- Update the source map / index links; fix broken links; remove pointers to
  deleted surfaces.
- Strip capability narrative that belongs in VISION or the capability ledger.

### VISION.md (ambition + progress marker)

- Restate the eventual goal if it shifted (only on explicit user direction;
  otherwise preserve it verbatim).
- Update the **living progress marker**: which primitives/milestones are now live,
  which are in flight, which remain — each citing evidence.
- Name honesty-debts openly (looks-done-but-isn't items). Do not hide regressions.
- Mark the current position on the path: "where we stand toward the goal."

## 3. Phase 3 — Prune redundancy + cull husks (P8)

Across the whole context surface (`.github/` + the three docs + loose project assets):

- Collapse duplicate authority: exactly one home per fact.
- Archive superseded planning under the archive (PROJECT.md §3); do not delete
  when historical value remains.
- Delete contradicted or dead instructions (broken paths, retired surfaces, stale
  commands).
- Remove bloat that hides an executable instruction.
- **Cull spent assets (P8), two-step:** a loose script, one-off test, spent
  scaffold, convenience hack, throwaway unblocker that never entered a real
  module — **(1) extract its lesson** into durable seed context (a protocol, an
  agent, the three references, a comment, a ledger row), **(2) then hand to
  `undertaker` to cull.** Never cull a lesson unrecorded. Never cull the in-flight
  (a scaffold still producing a needed metric has utility — keep it).

Run `hygiene` ([./hygiene.md](./hygiene.md)) for a deeper ranked pass when the
redundancy is non-trivial.

## 4. Phase 4 — Evolve agents + protocols to fit the project (gated)

The pot re-shapes to the plant. As the project's real patterns stabilize, fold
them into the agent/protocol stable so future agents are sharper *here* — without
weakening the portable core.

Candidate evolutions:

- Bind a recurring project pattern into an agent's Rules/Scope (e.g. a real
  choke-point file, a project-specific verification step).
- Add a project-specific row to the regression capability matrix
  ([./regression_protocol.md](./regression_protocol.md) §4) or PROJECT.md §7.
- Sharpen an agent description so the picker selects it correctly for this domain.
- Create a new agent ONLY when a durable, distinct role has emerged (orchestrator
  agent-creation rule). Merge/retire agents whose role this project never exercises.
- Promote a proven ad-hoc workflow into a protocol; retire a protocol this project
  never runs (archive it under PROJECT.md §3 if it has reference value).

Gates:

- **Principle-preserving.** Never dilute [../copilot-instructions.md](../copilot-instructions.md)
  or the universal protocol principles to fit one project. Project facts go in
  PROJECT.md or an agent's project-bound section, not by softening a global rule.
- **Ask before** creating/deleting an agent, changing a public protocol contract,
  or editing the constitution. Editing PROJECT.md and tightening an agent's
  project-scoped rules is in-bounds when the user invoked this protocol.
- One change-class at a time; record each evolution in the reality map.

## 5. Phase 5 — Verify

- **Docs/agents/protocols only (no shipped runtime):** `agent_tooling/link_check.py`
  (every link resolves), `agent_tooling/bloat_lint.py` (register held), and a
  stale-reference search (old agent names, deleted protocols, dead paths). State
  `doc-only no deploy`.
- **If a PROJECT.md command or core-flow binding changed:** run the local gate via
  `agent_tooling/project.py gate` to confirm the bound commands still resolve and pass.
- Confirm demarcation holds: grep each doc for the other two docs' responsibilities
  leaking in.
- `agent_tooling/run_all.py` is the one-command full sweep for this phase.

## 6. Sign-off

Report:

| Doc / surface | Action | Demarcation | Evidence |
| --- | --- | --- | --- |
| AUTODEV.md | updated/established | gotchas only | probes cited |
| README.md | updated/established | structure only | links resolve |
| VISION.md | updated/established | goal+progress only | markers cited |
| pruning | n removed / n archived | — | — |
| agent/protocol evolution | n changed | core intact | gate |

Completion line:

```text
context_evolution COMPLETE -- 3 docs reconciled, redundancy pruned <n>, stable evolved <n>, demarcation held, <doc-only no deploy | local gate green>
```

## Hard Rules

- Three docs, three responsibilities, zero overlap.
- A detected doc-vs-code lie is stop-the-line: fix the doc in the same cycle, before any other evolution. A lying doc drops first-try success below the no-docs baseline (PART 0 T5).
- No claim without evidence; no aspiration stated as current fact.
- Prune redundancy every run; one home per fact.
- Evolve the stable to fit the project, never by weakening the portable core.
- Ask before agent creation/deletion, public-contract changes, or constitution edits.
- Establish a missing doc from real state; never fabricate to fill a template.
