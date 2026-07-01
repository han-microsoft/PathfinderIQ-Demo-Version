# agent_tooling — SPEC

Low-level general-purpose tools. Any agent uses them as it sees fit. Each
shortcuts a boring, repeated developer function. Speed + reproducibility serve
the seed mission.

## Binding contract (every tool obeys)

Tools must obey the laws they serve. A tool that violates them is a lie.

- **Zero deps.** Python 3 stdlib only. No pip. No bash beyond POSIX `sh`.
- **One job each (P1/P2).** No god-script. Shared logic flows from `lib.py`.
- **Read-only by default.** Detectors detect; agents fix. Only `nonce`,
  `new_finding`, `record_metric` write — and only to scratch/findings/evidence.
- **Exit code = verdict.** `0` pass, `1` violation/fail, `2` usage/internal error.
  So every audit tool doubles as a CI/gate check.
- **Structured output.** Human lines by default; `--json` where a machine consumes it.
- **Deterministic (P4).** Same input -> same output + same exit. No clock in verdicts
  (except `nonce`).
- **Resolve, never hardcode.** Project facts come from `project get <KEY>`
  (PROJECT.md §0 bindings). No path/command literal in any tool.
- **Bounded.** No unbounded walk into `.git`, `node_modules`, `.venv`, `__pycache__`.

## Language choice rule

- **Python** when: parsing, AST, structured output, cross-file analysis, anything
  beyond ~15 lines of logic. = all analyzers.
- **Bash/sh** when: pure git/coreutils glue, no parsing, <10 lines. = `nonce`, `changed`.
- Tie -> Python (one runtime, portable, testable).

---

## The suite (12 tools + shared lib)

### Bind layer

| Tool | Lang | Job | Exit |
| --- | --- | --- | --- |
| `project` | py | Resolve a binding from PROJECT.md §0. `project get GATE_TEST`, `project tier`, `project gate` (run the bound gate), `project all --json`. The keystone every other tool calls. | 0 ok / 1 unset-required / 2 usage |

### Reproducibility glue

| Tool | Lang | Job | Exit |
| --- | --- | --- | --- |
| `nonce` | sh | Mint `<PREFIX>_<UTCstamp>`. Default prefix `RUN`. The run id every evidence/regression cycle stamps onto created artefacts. | 0 |
| `new_finding` | py | Stamp a findings file at `<FINDINGS_DIR>/<agent>_<YYYYMMDD>_<slug>.md` with a skeleton. Enforces the naming convention. Prints the path. | 0 / 2 |
| `changed` | sh | Git changed files since a ref (default: working tree + staged). Scopes an audit to the diff. `changed main` / `changed --names`. | 0 / 2 |
| `record_metric` | py | Append `{ts,nonce,metric,value,threshold,result}` JSONL to the evidence dir (P7). Turns "I checked" into recorded evidence. `--fail-on-miss` exits 1 if value misses threshold. | 0 / 1 / 2 |

### Legibility self-audits (run the falsifiable tests; nonzero = violation)

| Tool | Lang | Job (principle) | Exit |
| --- | --- | --- | --- |
| `link_check` | py | Every markdown link + referenced relative path resolves (T5 drift). Scans `.md` under a root. | 0 / 1 |
| `bloat_lint` | py | Register enforcer (P3): flag articles/hedging/filler/emoji in seed + docs. `--strict` for seed files. | 0 / 1 |
| `dup_scan` | py | Duplicated code/text blocks (P1): normalized N-line window hash, report colliding spans. | 0 / 1 |
| `module_size` | py | LOC census per file; flag modules over a threshold (P5 god-module candidates). `--max 600`. | 0 / 1 |
| `cycle_scan` | py | Import-cycle detector (P1 DAG). Python `import`/`from` graph -> Tarjan SCC. `assumes:` Python; skips other langs with a note. | 0 / 1 |
| `secret_scan` | py | Hardcoded creds/keys/tokens/connection-strings (safety). Pattern set + entropy heuristic. | 0 / 1 |
| `boundary_check` | py | Env reads (`os.getenv`/`os.environ`) outside the `CONFIG_MODULE` (config boundary §6). Resolves the module from bindings. | 0 / 1 |

### Shared

| File | Job |
| --- | --- |
| `lib.py` | One home (C1) for: bindings parse, repo-root find, bounded file walk, ignore set, color/plain print, `--json` envelope. Every py tool imports it. |

---

## Cross-cutting behaviour

- **Self-application.** Run against this seed repo, the audit tools must pass (or
  report only known, named exceptions). The suite proves itself (P7).
- **`run_all`** (py) — convenience: run every read-only audit, one digest table,
  exit 1 if any fails. The single command an agent or CI calls. Not a god-script —
  it only dispatches the others.
- **Ignore set** (shared): `.git`, `node_modules`, `.venv`, `__pycache__`,
  `dist`, `build`, `*.lock`, binary blobs.

## Discoverability

- One line in `copilot-instructions.md` points agents at `agent_tooling/`.
- `agent_tooling/README.md` indexes each tool: name, one-line job, principle served.
- Tools are opt-in. Agents call them when useful, never forced.

## Acceptance (this build)

```text
agent_tooling COMPLETE -- 12 tools + lib + run_all, zero deps, every tool exit-coded,
self-audit green on seed (or named exceptions), discoverability wired
```
