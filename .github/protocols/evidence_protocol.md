# VM-agent Evidence Protocol

Every change, feature, or capability gets a mandatory planning phase that names the **concrete metrics, hard evidence, and test protocol** by which it will be conclusively judged complete. No batch output, no “looks fine”, no anecdotal screenshot stands in for measurement. Evidence comes from sequences and timings, not vibes.

## Why

- Anecdotal observation cannot distinguish a feature that works from a feature that appears to work. A fast-batched response looks identical to a streamed one at the end of the wire.
- Without a pre-declared metric, the threshold to declare PASS drifts toward whatever the implementation happens to produce.
- The cost of inventing the metric after the fact is a hidden regression: silent batching, dropped tokens, vanished audit events, lost session continuity.

## Rule

Before code is written, three artefacts exist in the change ledger:

1. **Definition** — what the feature *is* in falsifiable terms. One paragraph. No marketing words.
2. **Evidence plan** — the metrics that will be measured, the thresholds that count as PASS, and the falsifying signals that prove FAIL.
3. **Test protocol** — the exact procedure that will produce those metrics, run live where applicable, with artefacts written to `_snapshots/`.

No PASS without all three.

## Definition Section — required fields

- Capability name. One short noun phrase.
- One paragraph defining what observable behaviour proves it exists. Names the surfaces, the units, the success/failure shape.
- “What this is NOT” line. Banishes adjacent definitions that the metric must not be fooled into accepting.

## Evidence Plan — required fields

| Field | Content |
|---|---|
| Layer | The boundary being measured (e.g. model → CLI, CLI → stdout, PTY → operator). |
| Clock | Embedded timestamp, wall-clock receive, or both. |
| Metric | Concrete number with units (ms, count, ratio, bytes). |
| PASS threshold | Quantified bound. |
| FAIL signal | The opposite shape that the metric must reject. |
| Source artefact | The file or stream the number is derived from. |

Every metric ties to at least one falsifying signal. If a metric has no opposite that would prove FAIL, it is a vibe metric and does not count.

## Test Protocol — required shape

- Pre-flight: environment, image SHA, nonce, deploy state.
- Procedure: the exact commands or script invocations, in order.
- Artefact paths: where raw evidence is written.
- Acceptance: per-metric numeric assertion table.
- Cleanup ledger: created vs retained vs blocked.

The procedure must be re-runnable by another agent or by the user without prior context.

## Human-POV acceptance — required for operator-facing capabilities

For any capability a human reaches through the chat / IDE surface (not a pure internal/API contract), a signed `*_OK` probe is **necessary but not sufficient**. The capability is judged complete only when it ALSO passes a **human-POV acceptance**: an operator-phrased instruction, through the actual chat surface, with NO tool/skill/index/parameter hand-holding, succeeds end-to-end.

- The agent is driven as a real user would drive it: ONE chat turn carrying the natural-language intent (the operator's *words*, not the artifact's internal ids/tool names), no direct tool invokes for the work.
- **PASS** = the operator's intent is satisfied (the artifact exists + meets its bar) AND the trace shows the agent **discovered + assembled** the capability itself (search → instantiate/dispatch → execute), not a hardcoded path.
- **FAIL signal** = the signed probe is green but a human-phrased request does **not** succeed — i.e. the capability works only when spoon-fed exact tool calls. That is a product failure even though the mechanism passes.
- Drive + verify per [capability_workflow_protocol.md](capability_workflow_protocol.md) §4; record the exact human turn + the agent's tool trace + the independent artifact verification in `_snapshots/<capability>_e2e_<nonce>.json`.
- A signed probe proves the **mechanism**; the human-POV lane proves the **product**. Operator-facing work needs both; internal-only contracts (wire shapes, persistence, gating) need only the signed probe.

## Test Data Hygiene — inviolable

**The test creates. The test deletes only what the test created. The test does not touch anything else.**

- Every data asset a test produces (blob, file, row, index document, Lakehouse, Eventhouse, ontology, sandbox file, plan, audit row, session dir, etc.) is named with the current run nonce or otherwise nonce-tagged in a server-controlled field. Nonce ownership is the only acceptable proof of test ownership.
- Resources not created by the current run are immutable from the test’s point of view. The test may read, list, sample, hash, and reference them. The test may not write, append, rename, retag, reindex destructively, truncate, or delete them.
- After acceptance, the test deletes every asset it created when a safe delete tool exists. The delete tool must re-verify nonce ownership immediately before the delete and refuse otherwise.
- When no safe delete tool exists for an asset class, the test records `retained_with_reason` in the cleanup ledger with the exact resource id/path/tag and the cleanup owner. This is allowed only when there is no nonce-aware delete; it is never a shortcut.
- Any attempt to mutate a non-test-created data source is a stop-the-line failure for the whole protocol run. The run is marked FAIL and the offending step is recorded verbatim.
- Shared dev test indices/databases/lakehouses (e.g. `vmagent-test-dummy`, `vm_agent_tests` workspace folder) are containers, not assets. The test may create nonce-owned documents inside them and must delete those documents on cleanup, but it may not reset, drop, or destructively reindex the container itself unless the test was authored specifically as the destructive admin protocol for that container with explicit pre-run approval.
- Cleanup runs even when the test FAILs. A failed test still owns its created assets and must still delete them or record `retained_with_reason`.

The completion summary names, per asset class: created count, deleted count, retained-with-reason count, and blocked count. A passing test with non-zero retained-with-reason must justify each retention in plain text.

## Hard Rules

- No PASS without all three artefacts.
- No metric without a falsifying signal.
- No final-output-only evidence when the claim concerns process behaviour (streaming, ordering, latency, interleaving, recovery).
- No comparison against the same artefact that was used to design the feature. Evidence comes from independent measurement.
- No threshold invented after the run. Thresholds are declared in the Evidence Plan before the live procedure starts.
- Evidence files live under `_snapshots/` (or another auditable location named in the plan). Console-only output is not evidence.
- A test protocol that cannot fail is broken. Every protocol exercises at least one negative path that would have caught a previous mistake.
- **No mutation of a data source the test did not itself create.** Read freely; write only nonce-owned new things; delete only those.
- **Cleanup is part of PASS.** A test that cannot account for every asset it created — deleted or retained-with-reason — is FAIL.
- The completion summary names the active image SHA, the nonce, every metric value vs threshold, the artefact paths, and the cleanup ledger.
