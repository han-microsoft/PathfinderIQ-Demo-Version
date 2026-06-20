# Protocol: Foundation Strengthening

Prepare VM-agent codebase for DAA work in [../../build_spec/vm_agent_northstar_design.html](../../build_spec/vm_agent_northstar_design.html).

Success means material support for future DAA code work: safer contracts, cleaner package shape, stronger tests, removed dead weight, clearer verification hooks, or reduced implementation ambiguity. Docs-only cleanup can be part of the run, but cannot be the whole pass when safe code/config/test actions exist.

## Use When

- User asks to clean, organize, or harden foundation before DAA implementation.
- Work spans structure, defects, dead code, docs, and capability readiness.
- Orchestrator owns execution.

## Flow

```text
context map
  -> parallel read-only specialist audits
  -> consolidated motive vectors
  -> central action plan
  -> execution sections
  -> specialist fixes in sequence
  -> regression_protocol loop
  -> pay findings forward
```

## Entry Conditions

- Work stays inside `vm_agent/`.
- Active authorities:
  - [../../build_spec/vm_agent_northstar_design.html](../../build_spec/vm_agent_northstar_design.html)
  - [../../build_spec/CURRENT_STATE.md](../../build_spec/CURRENT_STATE.md)
  - [../../AUTODEV.md](../../AUTODEV.md)
  - [../../vmagent/README.md](../../vmagent/README.md)
  - [regression_protocol.md](./regression_protocol.md)
- No live write probe, deploy, cloud mutation, or destructive deletion without explicit authorization.

## 1. Context Map

Orchestrator reads:

- north-star design current-state, task matrix, architecture, safety, roadmap;
- capability register and known blockers;
- package map;
- regression protocol;
- current repo layout.

Output if non-trivial:

```text
build_spec/orchestrator_<YYYYMMDD>_foundation_strengthening.md
```

## 2. Specialist Audit Pass

Run these agents read-only first:

| Agent | Scope | Output |
| --- | --- | --- |
| `inquisitor` | package boundaries, layering, duplicate flow, wrong abstractions | structural findings |
| `undertaker` | unused files/symbols/docs/config, archived planning residue | deletion candidates with reachability proof |
| `bug_hunter` | latent defects, silent failures, races, validation gaps | defect register |
| `documentation_curator` | README/AUTODEV/capability/protocol drift and bloat | doc findings |

Parallel allowed only for read-only audits. No edits during audit pass.

## 3. Consolidate

Create central plan with rows:

```text
Finding | Source agent | Duplicate of | Motive vector | Action | Owner | Status
```

Motive vectors:

- `safety`: auth, secrets, target allowlists, destructive writes.
- `state`: durability, FSM, replay, cleanup, retained resources.
- `contract`: CLI/API/MCP/schema/event drift.
- `operability`: deploy, regression, observability, diagnostics.
- `shape`: package boundary, duplicated flow, wrong abstraction.
- `experience`: UI/operator friction.
- `knowledge`: docs, protocols, agent contracts, capability register.

## 4. Action Plan

For each action:

```text
ID | Motive vector | Owner agent | Files | Change shape | Gate | Verification
```

Classify:

- `do-now`: low blast radius, strong payoff, materially supports future code work.
- `code-now`: safe code/config/test change that removes a blocker or hardens foundation.
- `docs-now`: documentation/pay-forward change paired to a code or blocker finding.
- `defer`: real issue but not prerequisite.
- `blocker`: needs external permission, cloud/RBAC/network change, or user decision.
- `reject`: not a defect after consolidation.

The plan must include at least one `code-now` action unless the audit proves every material code action is unsafe, externally blocked, or belongs to a later named vertical slice.

## 5. Authorization Gate

Before edits, present:

- selected `do-now` actions;
- deferred/blocker actions;
- files to change;
- verification plan;
- explicit yes/no ask.

No source edits before user authorization unless user already gave explicit direct-cleanup authorization.

If user has already granted autonomous foundation-strengthening authority, proceed without re-asking unless action hits a safety gate.

## 6. Execute

Dispatch one owner at a time:

| Change | Owner |
| --- | --- |
| implementation / code hardening | `developer_vmagent` or `bug_hunter` |
| structural refactor | `inquisitor` |
| dead-code removal | `undertaker` |
| docs/protocol/capability updates | `documentation_curator` |
| terminal/UI prep | `couturier` |

No parallel edits. After each owner returns, orchestrator updates central plan status.

## 7. Verify

- Docs-only: link/path grep plus diagnostics.
- Code/config changes: local gate from [regression_protocol.md](./regression_protocol.md) §2.
- Shipped behavior changes: deploy and live regression from [regression_protocol.md](./regression_protocol.md) §§3-7.
- Any regression failure triggers fix-forward loop. Do not mark done until pass or genuine blocker.

## 8. Pay Forward

Record durable learnings:

```text
Learning | Destination | Change | Reason
```

Destinations:

- [../../build_spec/CURRENT_STATE.md](../../build_spec/CURRENT_STATE.md) for capability truth/blockers.
- [../../AUTODEV.md](../../AUTODEV.md) for operator gotchas.
- [regression_protocol.md](./regression_protocol.md) for new proof obligations.
- agent contracts for recurring role/process changes.
- `build_spec/Deprecated Planning/` for historical-only material.

## Sign-off

Report:

| action | owner | status | verification | pay-forward |
| --- | --- | --- | --- | --- |

Completion requires:

- no stranded finding;
- every action done/deferred/blocked/rejected;
- material code/config/test support for future DAA work, or explicit proof none was safe in this pass;
- verification recorded;
- pay-forward recorded or explicitly unnecessary.

## Hard Rules

- No edits outside `vm_agent/`.
- No unscoped cleanup.
- No bypassing specialist authorization gates.
- No parallel edits.
- No final PASS without regression proof or doc-only rationale.
- No docs-only PASS when safe material code/config/test action exists.
- No new agent/protocol unless durable role/workflow exists.
