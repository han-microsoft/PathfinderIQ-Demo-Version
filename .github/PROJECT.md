# PROJECT.md — Project Binding Manifest (vm_agent)

**The ONLY file an agent author fills when seeding. Every agent + protocol in
`.github/` references the roles defined here by name; fill the fields and the
whole stable binds to this repo without editing any agent or protocol file.**

vm_agent binding. The portable tooling (`agent_tooling/`, `graph_tooling/`,
`evals/`) resolves all project facts from the `## 0. Bindings` block below.

Rules:
- `REQUIRED` fields must be set before agents run real work.
- `OPTIONAL` fields may stay `none`; agents skip the bound behaviour.
- Exact paths/commands. Agents read them literally.
- A fact changes (new command, moved ledger) -> update HERE only.

---

## 0. Bindings (machine-readable)

The prose tables below *describe*; this block *binds*. One home (C1). Tools parse
this block via `project get <KEY>`.

Format: `KEY = value`, one per line, `#` comments ignored, `none` = unset.

```ini
# --- identity ---
PROJECT_NAME = vm-agent
PRIMARY_LANGS = python,typescript
LIVE_TARGET = none              # templated FQDN: https://pathfinderiq-aemo.<env-default-domain>/ — set with --target on evals

# --- scope (§2) ---
SCOPE_ROOT = .
CONTEXT_READ_ROOT = .
OFF_LIMITS = none               # parent GridIQ monorepo is outside this workspace; constitution governs it

# --- doc ledgers (§3) ---
CAPABILITY_LEDGER = build_spec/CURRENT_STATE.md
GOTCHA_LOG = AUTODEV.md
NORTHSTAR = build_spec/vm_agent_northstar_design.html
PACKAGE_MAP = vmagent/README.md
FINDINGS_DIR = build_spec/findings
ARCHIVE_DIR = build_spec/Deprecated Planning

# --- commands (§4) ---
GATE_COMPILE = python3 -m py_compile $(find vmagent -name '*.py' | sort)
GATE_TEST = PYTHONPATH=. pytest -q tests/test_cli_help.py
GATE_EXTRA = PYTHONPATH=. python3 scripts/validate_skills.py
BUILD = none
DEPLOY = ./deploy_vm_agent.sh --mode full --yes
VERIFY = ./deploy_vm_agent.sh --mode verify --yes
ENV_BOOTSTRAP = set -a && source .env && set +a && az account set --subscription "$AZURE_SUBSCRIPTION_ID" -o none

# --- core-flow (§5) ---
CORE_FLOW_CHECK = python3 scripts/golden_path_probe.py
CORE_FLOW_PASS_SIGNAL = GOLDEN_PATH_PROBE_OK

# --- evals (§4) ---
EVALS_RUN = python3 .github/evals/eval.py run

# --- safety (§6) ---
CONFIG_MODULE = vmagent/config.py
SECRETS_POLICY = managed-identity-only

# --- rigor (§8) ---
RIGOR_TIER = standard

# --- graph data assets (optional) ---
GRAPH_DATA_GLOBS = none         # opt-in; e.g. toolsets/*.json,deploy/*.yaml to map config assets
```

---

## 1. Identity

| Field | Value |
| --- | --- |
| Project name | vm-agent |
| One-line purpose | Tenant-resident data-asset compiler + operator IDE on Azure Container Apps (agentkit MAF runtime, MI-only cloud access). |
| Primary language(s) | Python (backend/tooling), TypeScript (React `ui/`) |
| Live target / deploy surface | Container App `pathfinderiq-aemo` (templated FQDN; pass `--target` to evals) |

## 2. Scope Roots

This workspace folder **is** the vm_agent repo; everything in it is writable. The
parent GridIQ monorepo (`../`) is outside the workspace and read-only per the
constitution ([copilot-instructions.md](copilot-instructions.md) scope rule).

| Field | Value | Note |
| --- | --- | --- |
| `SCOPE_ROOT` (agents write only here) | `.` | the whole vm_agent repo |
| `CONTEXT_READ_ROOT` (read for context) | `.` | — |
| Off-limits paths | `none` | GridIQ parent is outside the workspace already |

`SCOPE_ROOT` also scopes the dependency graph. The graph extractors cover
Python / Markdown / Shell (no TypeScript extractor), so `ui/` TS is out of the
graph regardless; the Python core (`vmagent/`, `scripts/`, `tests/`, `agentkit/`)
is what gets mapped.

## 3. Doc Ledgers

| Role | Path |
| --- | --- |
| Capability ledger (current-state truth) | `build_spec/CURRENT_STATE.md` |
| Gotcha log (operational landmines) | `AUTODEV.md` |
| Ambition / north-star | `build_spec/vm_agent_northstar_design.html` |
| Package map / boundary doc | `vmagent/README.md` |
| Findings directory | `build_spec/findings/` |
| Archive for deprecated planning | `build_spec/Deprecated Planning/` |

Findings naming: `build_spec/findings/<agent>_<YYYYMMDD>_<slug>.md`.

## 4. Commands

| Role | Command |
| --- | --- |
| Local gate — compile | `python3 -m py_compile $(find vmagent -name '*.py' | sort)` |
| Local gate — fast tests | `PYTHONPATH=. pytest -q tests/test_cli_help.py` |
| Local gate — extra validator | `PYTHONPATH=. python3 scripts/validate_skills.py` |
| Build | `none` (image built by deploy script) |
| Deploy | `./deploy_vm_agent.sh --mode full --yes` |
| Post-deploy verify | `./deploy_vm_agent.sh --mode verify --yes` |
| Live UX-flow evals | `python3 .github/evals/eval.py run` |
| Env/secret bootstrap | `set -a && source .env && set +a && az account set --subscription "$AZURE_SUBSCRIPTION_ID" -o none` |

The full pytest suite (`PYTHONPATH=. pytest -q`) is the broad gate; the fast
`test_cli_help.py` row is the cheapest correctness check bound to `GATE_TEST`.

## 5. Core-Flow Check

The single end-to-end proof the compiler chain still works after a change.

| Field | Value |
| --- | --- |
| Core-flow check command | `python3 scripts/golden_path_probe.py` |
| Pass signal | `GOLDEN_PATH_PROBE_OK` |
| What it exercises | discover -> adapt -> plan -> confirm -> materialize -> verify -> publish -> render -> blind-consume -> profile-gate -> cleanup |
| Test-isolation nonce convention | nonce-suffixed scratch resources (`vmagent_demo_*` / `vmagent-test-*`); existing data immutable |

Requires the live deploy + a signed dev key. Local-only changes gate on the
local gate; runtime/contract changes gate on golden + live regression.

## 6. Safety Specifics

Layered on top of the universal safety gates in `copilot-instructions.md`.

- Secrets: **managed identity only** — no keys, SAS, connection strings, account keys, or admin keys.
- Config boundary: **only `vmagent/config.py` reads env** (`os.getenv`/`os.environ`). Enforced by `boundary_check.py` (scope the check to `vmagent/`; reads in `scripts/`, `tests/`, `gridsfm_poc/` are legitimate non-package tooling).
- Auth/security surfaces that must never weaken: Entra bearer + Ed25519 dev-sign; CSP (`frame-src 'self' login.microsoftonline.com`, `connect-src … wss:`, no CDN); session ownership scoping.
- Destructive-action allowlist: write tools require explicit `confirmation`; only nonce-owned scratch resources created/rolled back; existing cloud data immutable.
- Dependency policy: **ask before adding any dependency** (the prodiq tooling is stdlib-only; no new deps).

## 7. Tech Stack Notes

- FastAPI backend (`vmagent/api`), agentkit MAF runtime (`vmagent/runtime/maf`), tool registry choke point `vmagent/tools/registry.py::invoke_tool` (profile -> confirmation -> audit). 80 tools, 14 routers, 5 source adapters, DAA core (`vmagent/daa`).
- Cloud access MI-REST only via `vmagent/tools/transport` (`RestDataSourceAdapter` + breaker-protected `mi_request`).
- Container App pinned `min=max=1` — `/sandbox` is per-replica ephemeral; multi-replica fan-out falsely fails sandbox e2e (see `AUTODEV.md`).
- `vmagent/config.py` is the only env reader; `CHILD_ENV_EXPORTS` is the declared `/api/exec` subprocess env allowlist (drift-guarded by `tests/test_child_env.py`).
- `StreamEventType` changes must update the frontend exhaustive maps or the Docker `tsc` build fails.
- vm_agent-specific protocols (adapter, data_pipeline, tool_card, renderer, frontend_regression, llm_benchmark) live in `.github/protocols/` alongside the generic prodiq set.

## 8. Rigor Tier

| Field | Value |
| --- | --- |
| `RIGOR_TIER` | `standard` |

`standard` = full evidence + regression + ledgers + deploy gate. Raise to
`critical` per-change for auth/privilege/data-integrity surfaces
(`vmagent/daa/access.py`, auth, CSP) — mandatory threat-model note +
deductive proof. Drop to `prototype` for `gridsfm_poc/` spikes.
