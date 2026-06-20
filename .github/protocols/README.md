# Protocols

Reusable agent-runnable workflows. User invocation pattern:

> "Run this protocol (path)"

Agent reads the named protocol and executes it autonomously, only stopping on destructive ambiguity, genuine blockers, or explicit user interruption.

For complex multi-agent work, use `orchestrator` first. It chooses protocol, dispatches specialists, manages gates, and verifies completion.

## Index

- [regression_protocol.md](./regression_protocol.md) — Implement -> local gate -> deploy -> live regression -> observe -> fix-forward for VM-agent changes.
- [data_pipeline_acceptance_protocol.md](./data_pipeline_acceptance_protocol.md) — the standard data-platform acceptance doctrine: discovery-first → custom-script processing → materialize-or-record-blocker → verify-queryable → two eval sets → dual-verify → persist → cleanup. Entrypoint `scripts/eval/run_standard_eval.py` (`STANDARD_EVAL_OK`). The named acceptance battery the regression loop references.
- [data_workflow_acceptance_protocol.md](./data_workflow_acceptance_protocol.md) — single end-to-end data workflow (source blob → processing → sink → published contract → blind consume) against real named assets with pre-declared outputs.
- [foundation_strenghthening_protocol.md](./foundation_strenghthening_protocol.md) — multi-agent foundation cleanup before DAA work.
- [adversary_inquisitor_iteration.md](./adversary_inquisitor_iteration.md) — adversarial probe -> structural fix candidates -> authorized remediation -> regression.
- [hygiene.md](./hygiene.md) — inventory -> rank -> prune/rewrite one candidate at a time -> verify.
- [renderer_protocol.md](./renderer_protocol.md) — author a bespoke compiler card (DAA flow event → registry-resolved chat card). One file + one line; generic fallback never breaks.
- [tool_card_protocol.md](./tool_card_protocol.md) — author a bespoke tool card (tool name/family → registry-resolved chat card). One file + one line; schema-driven generic floor never shows raw JSON.
- [adapter_protocol.md](./adapter_protocol.md) — add a new managed-identity data source via `tools/adapter_base.py::RestDataSourceAdapter` (subclass + declare attrs + implement operations + wire one `registry_defs` module). The base owns transport + error only; `invoke_tool` is untouched.

## Invocation shapes

| User says | Agent runs |
|---|---|
| "Run regression_loop" | [regression_protocol.md](./regression_protocol.md) |
| "Run regression_protocol" | [regression_protocol.md](./regression_protocol.md) |
| "Standard regression on this change" | [regression_protocol.md](./regression_protocol.md) |
| "Run the standard eval" / "Standard data-platform eval" | [data_pipeline_acceptance_protocol.md](./data_pipeline_acceptance_protocol.md) |
| "Accept this data pipeline" / "Run the data-platform battery" | [data_pipeline_acceptance_protocol.md](./data_pipeline_acceptance_protocol.md) |
| "Run foundation strengthening" | [foundation_strenghthening_protocol.md](./foundation_strenghthening_protocol.md) |
| "Run adversary_inquisitor_iteration" | [adversary_inquisitor_iteration.md](./adversary_inquisitor_iteration.md) |
| "Iterate the candidates" | [adversary_inquisitor_iteration.md](./adversary_inquisitor_iteration.md) |
| "Run hygiene" / "Hygiene sweep" | [hygiene.md](./hygiene.md) |
| "Add a compiler card" / "New chat renderer" | [renderer_protocol.md](./renderer_protocol.md) |
| "Add a tool card" / "Render a tool result" | [tool_card_protocol.md](./tool_card_protocol.md) |
| "Add a data source" / "New adapter" | [adapter_protocol.md](./adapter_protocol.md) |
| "Run this protocol: `<path>`" | the file at that path |

## Authoring rules

- Dense bullets. No filler. Every line either an instruction the agent executes or a guardrail the agent honours.
- Protocols MAY compose each other — e.g. iteration protocol composes regression protocol. Always link, never duplicate.
- Hard rules section at the end of every protocol. Banned behaviours listed verbatim.
- One protocol per workflow. If a protocol has two top-level phases that diverge, split it.
