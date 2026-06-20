# PROJECT.md — example: TypeScript frontend (React + Vite)

Filled manifest for a React/Vite single-page app, static-hosted. Copy the
`## 0. Bindings` block + §-values into [../PROJECT.md](../PROJECT.md).

## 0. Bindings (machine-readable)

```ini
# --- identity ---
PROJECT_NAME = console-ui
PRIMARY_LANGS = typescript
LIVE_TARGET = https://console.example.com

# --- scope (§2) ---
SCOPE_ROOT = .
CONTEXT_READ_ROOT = .
OFF_LIMITS = dist,node_modules

# --- doc ledgers (§3) ---
CAPABILITY_LEDGER = docs/CURRENT_STATE.md
GOTCHA_LOG = docs/GOTCHAS.md
NORTHSTAR = none
PACKAGE_MAP = README.md
FINDINGS_DIR = docs/findings
ARCHIVE_DIR = docs/archive

# --- commands (§4) ---
GATE_COMPILE = npm run typecheck
GATE_TEST = npm run test -- --run
GATE_EXTRA = npm run lint
BUILD = npm run build
DEPLOY = npm run deploy
VERIFY = curl -fsS "$LIVE_TARGET" | grep -q '<div id="root">'
ENV_BOOTSTRAP = none

# --- core-flow (§5) ---
CORE_FLOW_CHECK = npm run test:e2e -- --project chromium
CORE_FLOW_PASS_SIGNAL = passed

# --- safety (§6) ---
CONFIG_MODULE = src/config.ts
SECRETS_POLICY = no-secrets-in-bundle

# --- rigor (§8) ---
RIGOR_TIER = standard

# --- graph data assets (optional) ---
GRAPH_DATA_GLOBS = src/fixtures/*.json
```

## Notes

- **Local TS check != CI TS check**: the editor language server may pass while the
  pinned `tsc` in the build fails. `BUILD` (Docker/CI `tsc`) is authoritative.
- **No secrets in bundle**: anything in the client bundle is public; keep keys server-side.
- **Core flow**: a Playwright golden-path spec is the regression gate.
- The graph's Python extractor does not parse TS; `graph build` maps the repo's
  `.md`/`.py`/`.sh` and declares TS coverage as a gap (honest, not silent).
