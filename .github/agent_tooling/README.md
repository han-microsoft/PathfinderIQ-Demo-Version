# agent_tooling

Low-level general-purpose tools. Any agent calls them as it sees fit. Each
shortcuts a boring, repeated developer function. Zero deps (Python 3 stdlib +
POSIX sh). Spec: [SPEC.md](SPEC.md).

## Contract

- **Exit code = verdict.** `0` pass, `1` violation/fail, `2` usage. Every audit
  doubles as a gate/CI check.
- **Read-only** except `nonce`, `new_finding`, `record_metric`.
- **Resolve, never hardcode.** Project facts via `project get <KEY>` (PROJECT.md §0).
- `--json` on the analyzers for machine consumption. `--exclude SUBSTR` to scope.

## Tools

| Tool | Lang | Job | Principle |
| --- | --- | --- | --- |
| `project.py` | py | resolve a binding (`get`/`all`/`tier`/`gate`/`path`/`tools`/`seed`). Keystone. | — |
| `nonce.sh` | sh | mint `<PREFIX>_<UTCstamp>` run id | P7 |
| `new_finding.py` | py | stamp `<FINDINGS_DIR>/<agent>_<date>_<slug>.md` | T5 |
| `changed.sh` | sh | git changed files since a ref | — |
| `record_metric.py` | py | append metric+threshold+result JSONL to evidence | P7 |
| `link_check.py` | py | every md link + path resolves (drift) | T5 |
| `bloat_lint.py` | py | flag prose-bloat; hard=emoji/pleasantry, soft=filler/hedge | P3 |
| `dup_scan.py` | py | duplicated logic blocks (ignores import boilerplate) | P1 |
| `module_size.py` | py | LOC census; flag god-module candidates | P5 |
| `cycle_scan.py` | py | python import-cycle detector | P1 |
| `secret_scan.py` | py | hardcoded creds/keys/tokens tripwire | safety |
| `boundary_check.py` | py | env reads outside `CONFIG_MODULE` | §6 |
| `run_all.py` | py | run every audit, one digest, aggregate exit | — |
| `lib.py` | py | shared home: bindings parse, walk, output (C1) | P1 |

## Use

```sh
python3 .github/agent_tooling/project.py tools           # live registry (from docstrings)
python3 .github/agent_tooling/project.py seed            # readiness: which PROJECT.md bindings still unset
python3 .github/agent_tooling/run_all.py                 # full audit, one table
python3 .github/agent_tooling/project.py gate            # run the bound local gate
python3 .github/agent_tooling/link_check.py --json       # machine output
N=$(sh .github/agent_tooling/nonce.sh REGRESSION)        # mint a run nonce
python3 .github/agent_tooling/module_size.py --max 400   # tighter god-module bar
```

Seeding a new project: copy the closest [../PROJECT.examples/](../PROJECT.examples/)
manifest over [../PROJECT.md](../PROJECT.md), then run `project.py seed` until it
exits 0 (all required bindings set).

## Known exceptions on this seed

- `bloat_lint` exempts the register/philosophy docs — they must list the banned
  words to forbid them (same reason `secret_scan` skips its own pattern defs).

## Self-proof (P7)

`run_all` is green on the portable core. Every detector has a proven negative
path (fixture that makes it exit 1) — a check that cannot fail is broken.
