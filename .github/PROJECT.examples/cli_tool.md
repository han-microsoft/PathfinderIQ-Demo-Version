# PROJECT.md — example: CLI tool (prototype tier)

Filled manifest for a small Python CLI with no deploy surface. Shows the
`prototype` rigor tier: local gate only, ledgers optional, no live regression.
Copy the `## 0. Bindings` block + §-values into [../PROJECT.md](../PROJECT.md).

## 0. Bindings (machine-readable)

```ini
# --- identity ---
PROJECT_NAME = logmunch
PRIMARY_LANGS = python
LIVE_TARGET = none

# --- scope (§2) ---
SCOPE_ROOT = .
CONTEXT_READ_ROOT = .
OFF_LIMITS = none

# --- doc ledgers (§3) ---
CAPABILITY_LEDGER = none
GOTCHA_LOG = docs/GOTCHAS.md
NORTHSTAR = none
PACKAGE_MAP = none
FINDINGS_DIR = docs/findings
ARCHIVE_DIR = none

# --- commands (§4) ---
GATE_COMPILE = ruff check .
GATE_TEST = pytest -q
GATE_EXTRA = none
BUILD = none
DEPLOY = none
VERIFY = none
ENV_BOOTSTRAP = none

# --- core-flow (§5) ---
CORE_FLOW_CHECK = none
CORE_FLOW_PASS_SIGNAL = none

# --- safety (§6) ---
CONFIG_MODULE = none
SECRETS_POLICY = none

# --- rigor (§8) ---
RIGOR_TIER = prototype
```

## Notes

- **Prototype tier**: local gate is the ceiling; `DEPLOY = none` means local proof
  is the bar (P7 live-verify is N/A — no live surface). Agents say so in completion.
- **No core-flow check**: protocols fall back to the local gate only and state it.
- **Minimal ledgers**: a gotcha log is kept; capability ledger/north-star skipped
  (`none`) — agents skip the bound step and note it.
- Even at prototype tier, the universal laws still hold: errors stay visible, docs
  that exist stay true, no secrets hard-coded. The tier scales *ceremony*, not laws.
