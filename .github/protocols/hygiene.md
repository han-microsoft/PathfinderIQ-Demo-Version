# Protocol: Hygiene Sweep

Small, ranked cleanup pass for VM-agent docs, agents, protocols, code shape, and stale surfaces.

## Use When

- User asks for hygiene, pruning, simplification, or repo cleanup.
- User wants redundant agents/protocols/docs removed or tightened.
- Do not use for feature work; use `developer_vmagent`.

## Flow

```text
scope
  -> inventory
  -> ranked candidates
  -> one candidate at a time
  -> specialist agent or direct doc edit
  -> local/regression verification
```

## Entry Conditions

- Stay inside `vm_agent/`.
- Preserve active authorities:
  - [../../build_spec/vm_agent_northstar_design.html](../../build_spec/vm_agent_northstar_design.html)
  - [../../build_spec/CURRENT_STATE.md](../../build_spec/CURRENT_STATE.md)
  - [regression_protocol.md](./regression_protocol.md)
  - [../../AUTODEV.md](../../AUTODEV.md)
- Archive planning history under `build_spec/Deprecated Planning/`; do not create new loose planning docs.

## 1. Inventory

Write or update a short hygiene note only when the sweep is non-trivial:

```text
build_spec/hygiene_<YYYYMMDD>_<slug>.md
```

Inventory rows:

```text
path | role | keep / rewrite / delete / archive | reason
```

## 2. Candidate Ranking

Rank by:

1. duplicate authority;
2. GridIQ residue;
3. broken or misleading operational instruction;
4. dead agent/protocol role;
5. drift from capability register or regression protocol;
6. bloat that hides an executable instruction.

## 3. Action

One candidate at a time.

| Change | Owner |
| --- | --- |
| docs/protocol cleanup | `documentation_curator` or direct edit if user requested cleanup |
| dead file/agent/protocol removal | `undertaker` or direct edit if user requested pruning |
| structural code cleanup | `inquisitor` |
| defect hardening | `bug_hunter` |
| UI cleanup | `couturier` |
| implementation follow-through | `developer_vmagent` |

Ask before deleting files unless the user explicitly requested pruning of redundant files.

## 4. Verify

- Docs/protocol-only: path/link grep plus editor diagnostics.
- Code-affecting: local gate plus regression protocol where shipped behavior changes.
- Agent/protocol changes: search for stale agent names, GridIQ-only paths, deleted protocol references.

## Sign-off

Report:

```text
kept: <agents/protocols>
deleted: <files>
rewritten: <files>
verification: <checks>
```

## Hard Rules

- Keep agents few and legible.
- Delete roles with no distinct job.
- No GridIQ root paths in active VM-agent contracts unless explicitly marked historical.
- No new broad process docs when a ledger row suffices.
