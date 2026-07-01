# Protocol: Adversary -> Inquisitor Iteration

Hardening loop for a named VM-agent surface.

## Use When

- User asks for adversarial hardening.
- User names an API/tool/runtime/UI surface and wants attack findings turned into structural fixes.
- Do not use for ordinary implementation; use `developer_vmagent`.

## Flow

```text
surface named
  -> adversary probes and writes findings
  -> inquisitor ranks structural fix candidates
  -> user authorizes candidate fixes
  -> fix-mode agent implements
  -> regression_protocol verifies live behavior
```

## Entry Conditions

- Work remains inside `vm_agent/`.
- `vm_agent/.env` sourced and subscription pinned before live probes.
- Nonce prepared for live regression.
- User has authorized any write-shaped live adversarial probes.

## 1. Adversary Pass

- Invoke `adversary` on the named surface.
- Output: `build_spec/adversary_<YYYYMMDD>_<slug>.md`.
- Adversary never edits runtime code.
- If no finding is confirmed, record saturation note: classes tried, payload families, result.

## 2. Candidate Ranking

Rank confirmed findings by:

1. auth/data-boundary risk;
2. secret/key leakage risk;
3. sandbox/cloud target escape;
4. unbounded resource/cost path;
5. silent success or misleading contract;
6. repeated structural root cause.

Surface:

```text
Candidates:
1. <path/surface> — <finding ids> — <one-line reason>
```

## 3. Inquisitor Plan

- Invoke `inquisitor` on each selected candidate.
- Inquisitor writes remediation plan and asks for authorization.
- Do not patch until the user authorizes selected plan IDs.

## 4. Fix Dispatch

Pick one fix-mode agent:

| Fix shape | Agent |
| --- | --- |
| direct implementation / backend / tools / runtime | `developer_vmagent` |
| structural refactor | `inquisitor` |
| defect hardening | `bug_hunter` |
| dead code deletion | `undertaker` |
| docs only | `documentation_curator` |
| UI only | `couturier` |

Run one candidate at a time. No parallel edits.

## 5. Regression

Run [regression_protocol.md](./regression_protocol.md) after shipped behavior changes.

Expected blockers are allowed only when already listed in [../../build_spec/CURRENT_STATE.md](../../build_spec/CURRENT_STATE.md).

## Sign-off

Report:

| candidate | finding ids | fix agent | status | regression |
| --- | --- | --- | --- | --- |

Then one sentence naming the structural risk removed.

## Hard Rules

- No edits outside `vm_agent/`.
- No live write probe without explicit authorization.
- No fix without plan authorization unless user explicitly requested direct implementation.
- No candidate marked done without regression proof or explicit doc-only rationale.
- No rollback-as-fix; fix forward.
