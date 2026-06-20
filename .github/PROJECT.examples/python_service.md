# PROJECT.md — example: Python service (FastAPI + Azure)

Filled manifest for a Python backend service deployed to Azure Container Apps.
Copy the `## 0. Bindings` block + the §-values into [../PROJECT.md](../PROJECT.md).

## 0. Bindings (machine-readable)

```ini
# --- identity ---
PROJECT_NAME = orderflow-api
PRIMARY_LANGS = python
LIVE_TARGET = https://orderflow-api.azurecontainerapps.io

# --- scope (§2) ---
SCOPE_ROOT = .
CONTEXT_READ_ROOT = .
OFF_LIMITS = infra/secrets,deploy/.env

# --- doc ledgers (§3) ---
CAPABILITY_LEDGER = docs/CURRENT_STATE.md
GOTCHA_LOG = docs/GOTCHAS.md
NORTHSTAR = docs/VISION.md
PACKAGE_MAP = docs/PACKAGE_MAP.md
FINDINGS_DIR = docs/findings
ARCHIVE_DIR = docs/archive

# --- commands (§4) ---
GATE_COMPILE = ruff check . && mypy app
GATE_TEST = pytest -q
GATE_EXTRA = none
BUILD = docker build -t orderflow-api .
DEPLOY = ./deploy.sh --yes
VERIFY = curl -fsS "$LIVE_TARGET/health"
ENV_BOOTSTRAP = set -a && . ./control/.env && set +a && az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# --- core-flow (§5) ---
CORE_FLOW_CHECK = pytest tests/core_flow -q
CORE_FLOW_PASS_SIGNAL = passed

# --- safety (§6) ---
CONFIG_MODULE = app/config.py
SECRETS_POLICY = managed-identity-only

# --- rigor (§8) ---
RIGOR_TIER = standard

# --- graph data assets (optional) ---
GRAPH_DATA_GLOBS = app/fixtures/*.json,app/schemas/*.json
```

## Notes

- **Config boundary**: only `app/config.py` reads env; `boundary_check.py` enforces it.
- **Secrets**: managed identity only — no keys/connection strings in code or `.env`.
- **Deploy**: `ENV_BOOTSTRAP` pins the Azure subscription before any `az`/ACR call
  (avoids the silent subscription-drift failure).
- **Core flow**: a fast end-to-end test under `tests/core_flow/` is the regression gate.
