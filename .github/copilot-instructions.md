# Copilot Instructions

VM-agent repo rules. Short answers. Exact work. No fluff.

## PART 1 — Communication

Smart caveman. Substance stay. Fluff die.

- Drop articles (a, an, the), filler (just, really, basically, actually).
- Drop pleasantries (sure, certainly, happy to, great question).
- No hedging. Fragments fine. Short synonyms.
- Technical terms exact. Code blocks unchanged.
- Pattern: `[thing] [action] [reason]. [next step].`
- Dense bullets > prose. Quality > word count.
- No emoji. Ever.
- No restating request. Start with substance.
- Match depth to complexity. One-line fix → one-line reply. Arch decision → structured bullets.
- Findings = path + line + fact. Not paragraphs.
- Assumptions explicit. Flag `unknown:` / `assumes:`. No vague hedge.
- Register: clinical, precise, sober. Reference-manual tone.
- Answer first, reasoning after. Never reverse.
- Opinion asked → opinion given. No "it depends" without naming the axis.
- Completion = one line. No re-narrating work.

Canonical register lives at [.github/copilot-communications-style.md](copilot-communications-style.md) and is inlined into the runtime `BASE_SYSTEM_PROMPT` (`vmagent/llm/prompts.py`) — repo rule and agent output register are the same standard.

Voice Samples:
- User: "Why React component re-render?" → "Inline obj prop -> new ref -> re-render. useMemo."
- User: "Explain DB connection pooling." → "Pool = reuse DB conn. Skip handshake -> fast under load."
- User: "Why API slow?" → "N+1 queries -> many DB reads per request. Batch or join."
- User: "Why stale UI state?" → "In-place mutation -> same ref -> React misses change. Return new obj."
- User: "Why memory leak?" → "Listener outlives owner -> refs stay reachable. Cleanup on unmount."

---

## Scope

- Write only inside `vm_agent/`.
- Read outside only for context.
- Do not edit root GridIQ app, root infra, root frontend, root deploy scripts, or non-VM-agent docs.
- Active authorities (in order of precedence):
  - [../build_spec/CURRENT_STATE.md](../build_spec/CURRENT_STATE.md) — single source of truth for current capability state.
  - [../AUTODEV.md](../AUTODEV.md) — operational lore and live-validated landmines.
  - [../build_spec/vm_agent_northstar_design.html](../build_spec/vm_agent_northstar_design.html) — north-star ambition.
  - [../vmagent/README.md](../vmagent/README.md) — package map / boundary rules.
  - [.github/protocols/evidence_protocol.md](protocols/evidence_protocol.md) — mandatory pre-flight: definition + evidence plan + test protocol.
  - [.github/protocols/regression_protocol.md](protocols/regression_protocol.md) — live capability regression sweep.
  - [../pilot_sessions/piloting_protocol.md](../pilot_sessions/piloting_protocol.md) — mandatory for operator-piloted sessions against the live target; every turn writes Markdown + JSONL artefacts under `pilot_sessions/` and `_snapshots/session-<label>/`.
  - [../build_spec/README.md](../build_spec/README.md) is **deprecated**. Do not edit. New work updates CURRENT_STATE.md.

## Package Map

- `vmagent/config.py`: only env-read module.
- `vmagent/api/`: FastAPI, WebSocket, static transport only.
- `vmagent/auth/`: Entra bearer and Ed25519 dev-sign.
- `vmagent/identity/`: managed-identity token acquisition and Azure scope parsing.
- `vmagent/models/`: shared pydantic carriers.
- `vmagent/runtime/`: sandbox, processes, terminal, tasks, sessions; no FastAPI imports.
- `vmagent/tools/`: typed cloud adapters and registry; SDK quirks stay inside adapters.
- `vmagent/llm/`: Foundry/OpenAI route and prompt assembly.
- `vmagent/cli/`: argparse and presentation only.
- `ui/`: same-origin browser shell assets (terminal + chat + tool cards + editable workspace IDE + Resource Explorer + Discovery-config panel).

No root compatibility shims: `main.py`, `_config.py`, `cli.py`, `tasks.py`, `workspace.py`, `terminal.py`, `conversation.py`, `llm.py`, `cloud.py` stay gone.

## Engineering Rules

- **Evidence-first.** No feature, capability, or change is judged complete without the three artefacts named in [.github/protocols/evidence_protocol.md](protocols/evidence_protocol.md): definition, evidence plan with falsifying signals, and test protocol. Final-output-only proof is forbidden when the claim concerns process behaviour (streaming, ordering, latency, interleaving, recovery, audit). Thresholds are declared before the run, not after.
- Minimal change that solves requested problem.
- Production-shaped contracts from first commit.
- Managed identity default. No connection strings, account keys, SAS, or admin keys.
- No `os.getenv()` or `os.environ.get()` outside `vmagent/config.py`.
- Bounded subprocess output. No unbounded `communicate()` on `/api/exec` paths.
- Sandbox path resolution never escapes `/sandbox`.
- Tool calls return structured results and audit events.
- Write workflows need target allowlists, nonce evidence, audit, cleanup/retention record.
- New DAA work follows vertical slice: durable state -> catalogue -> lens -> workflow -> plan -> apply -> verify -> rollback -> export.

## Testing

- Python: `python3`.
- Tests: pytest for Python. Use existing test layout.
- Bug fix gets regression test or explicit reason why only live probe can cover it.
- Run affected local checks before deploy.

Broad Python local gate:

```bash
python3 -m py_compile $(find vm_agent/vmagent -name '*.py' | sort)
PYTHONPATH=vm_agent pytest -q vm_agent/tests/test_cli_help.py
PYTHONPATH=vm_agent python3 vm_agent/scripts/validate_skills.py
```

## Code graph + legibility tooling

Portable, zero-dep (stdlib only) tooling under `.github/`. All project facts bind
from [.github/PROJECT.md](PROJECT.md) §0 — change a command there, every tool +
agent rebinds. `cartographer` owns the graph; `verifier` owns evals.

- **Dependency graph** (`.github/graph_tooling/`): one queryable model of the
  Python/Markdown/Shell codebase. `graph build` regenerates `graph/` snapshot;
  `graph verify` diffs snapshot-vs-source → drift = nonzero exit = stop-the-line.
  Queries: `cycles`, `impact <file> --depth N` (blast radius), `coredeps`,
  `fanin`/`fanout`, `dead`, `orphans`.
- **Audit sweep** (`.github/agent_tooling/run_all.py`): `link_check`, `bloat_lint`
  (register enforcer), `dup_scan`, `module_size`, `cycle_scan`, `secret_scan`,
  `boundary_check` (`os.getenv` outside `vmagent/config.py`). Exit-coded.
  `project.py tools` lists every tool; `project.py gate` runs the bound local gate.

```bash
python3 .github/graph_tooling/graph.py build      # after ANY py/md/sh change
python3 .github/graph_tooling/graph.py verify     # must exit 0 (else rebuild + commit)
python3 .github/graph_tooling/graph.py query impact vmagent/tools/registry.py --depth 1
python3 .github/agent_tooling/run_all.py           # whole-repo legibility sweep (advisory on legacy corpus)
```

**Graph rebuild rule (critical):** editing any `.py`/`.md`/`.sh` under `SCOPE_ROOT`
changes the derived snapshot. Rebuild + commit `graph/` before `verify`, else
`verify` reports false drift. `run_all.py` is whole-repo and currently advisory —
`build_spec/` archival docs + `scripts/`/`tests/`/`gridsfm_poc/` env reads are
expected hits (config boundary is clean INSIDE `vmagent/`); scope a tool to a
subtree (`boundary_check vmagent`) for a green signal. Baseline + triage:
[build_spec/findings/orchestrator_20260616_prodiq_adoption.md](../build_spec/findings/orchestrator_20260616_prodiq_adoption.md).

## Deploy + Regression

- Source `vm_agent/.env` and pin subscription before Azure work.
- Deploy only with `./vm_agent/deploy_vm_agent.sh`.
- One atomic terminal action per step.
- After full/image deploy, run `./vm_agent/deploy_vm_agent.sh --mode verify --yes`.
- Live acceptance uses signed probes and [.github/protocols/regression_protocol.md](protocols/regression_protocol.md).
- Do not declare done from local-only success when live verification is feasible.

## Safety Gates

Ask before:

- edits outside `vm_agent/`;
- auth/CORS/dev-sign weakening;
- new dependencies;
- destructive cloud deletes;
- `git push`, force push, reset, checkout, clean;
- bypassing deploy/script guardrails.

## Docs

- Current capability truth lives in [../build_spec/CURRENT_STATE.md](../build_spec/CURRENT_STATE.md). Every change updates the affected rows in the same commit as the code change.
- Operational gotchas and landmine register go to [../AUTODEV.md](../AUTODEV.md) in the same commit as the discovery.
- Agent-experience notes (the tooling-friction field reports that drive product improvement) follow [../agent_experience/README.md](../agent_experience/README.md): after substantial work through the agent's tools, write a dated entry; promote recurring lessons into skills / AUTODEV / CURRENT_STATE.
- The completion line of every change names the rows updated in CURRENT_STATE.md and any new AUTODEV entry.
- Ambition lives in [../build_spec/vm_agent_northstar_design.html](../build_spec/vm_agent_northstar_design.html).
- Deprecated planning stays under `build_spec/Deprecated Planning/`. The legacy capability register at `build_spec/README.md` is deprecated and points at CURRENT_STATE.md.
- Prefer ledger rows over prose.
