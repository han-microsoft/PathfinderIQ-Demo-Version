#!/usr/bin/env bash
# ============================================================================
# Infrastructure Provisioner — Azure Resources Only
# ============================================================================
#
# Provisions Azure infrastructure ONLY. No scenario data.
# Scenarios are deployed separately via per-scenario deploy scripts.
#
# Pipeline:
#   1. Azure infrastructure (AI Foundry, AI Search, Storage, Cosmos)
#   2. App infrastructure (ACR, Container App, identity, RBAC) — optional
#
# Usage:
#   chmod +x deploy.sh && ./deploy.sh
#
# Options:
#   --skip-infra         Skip infrastructure provisioning (reuse existing Azure resources)
#   --app-infra          Deploy Container App infra (ACR, CAE, identity, RBAC) into existing RG
#   --env NAME           Use a specific azd environment name
#   --location LOC       Azure location (default: swedencentral)
#   --yes                Skip all confirmation prompts
#
# ============================================================================
set -euo pipefail

# ── Colour helpers ──────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✓${NC}  $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
fail()  { echo -e "${RED}✗${NC}  $*"; }
step()  { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${NC}\n"; }
banner() {
  echo -e "\n${BOLD}${CYAN}"
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  Graph Data Provisioner — Deployment                         ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

# ── Parse arguments ─────────────────────────────────────────────────

SKIP_INFRA=false
DEPLOY_APP_INFRA=false

AUTO_YES=false
AZD_ENV_NAME=""
AZURE_LOC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-infra)        SKIP_INFRA=true; shift ;;
    --app-infra)         DEPLOY_APP_INFRA=true; shift ;;

    --yes|-y)            AUTO_YES=true; shift ;;
    --env)               AZD_ENV_NAME="$2"; shift 2 ;;
    --location)          AZURE_LOC="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,/^set -euo/p' "$0" | head -n -1
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      echo "Run with --help for usage."
      exit 1
      ;;
  esac
done

# ── Locate project root ────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

# ── WSL path helper ─────────────────────────────────────────────────
# When running on WSL with the Windows az CLI (az.cmd via interop),
# /mnt/c/... paths must be converted to C:/... for az to find files.

_az_path() {
  local p="$1"
  if [[ "$p" == /mnt/[a-z]/* ]] && command -v wslpath &>/dev/null; then
    wslpath -m "$p"
  else
    echo "$p"
  fi
}

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"
CONFIG_TEMPLATE="$PROJECT_ROOT/azure_config.env.template"

# ── Helper: prompt user ────────────────────────────────────────────

confirm() {
  local msg="$1"
  if $AUTO_YES; then return 0; fi
  echo -en "${YELLOW}?${NC}  ${msg} [y/N] "
  read -r answer
  [[ "$answer" =~ ^[Yy] ]]
}

set_config() {
  local key="$1" val="$2"
  local d=$'\x01'
  local escaped_val="${val//\\/\\\\}"
  escaped_val="${escaped_val//&/\\&}"
  if grep -q "^${key}=" "$CONFIG_FILE" 2>/dev/null; then
    sed -i "s${d}^${key}=.*${d}${key}=${escaped_val}${d}" "$CONFIG_FILE"
  else
    echo "${key}=${val}" >> "$CONFIG_FILE"
  fi
  export "$key=$val"
}

choose() {
  local prompt="$1"; shift
  local options=("$@")
  echo -e "\n${YELLOW}?${NC}  ${prompt}"
  for i in "${!options[@]}"; do
    echo "   $((i+1))) ${options[$i]}"
  done
  while true; do
    echo -en "   Choice [1-${#options[@]}]: "
    read -r choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= ${#options[@]} )); then
      CHOSEN="${options[$((choice-1))]}"
      return 0
    fi
    echo "   Invalid choice."
  done
}

# ── Helper: auto-discover resources from existing Azure RG ─────────

discover_resources_from_rg() {
  local rg="$1"

  if ! az group show --name "$rg" &>/dev/null; then
    warn "Resource group '$rg' not found — cannot auto-discover resources."
    return 1
  fi

  info "Auto-discovering resources from resource group: $rg"

  AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv 2>/dev/null || true)
  [[ -n "$AZURE_SUBSCRIPTION_ID" ]] && set_config AZURE_SUBSCRIPTION_ID "$AZURE_SUBSCRIPTION_ID"
  set_config AZURE_RESOURCE_GROUP "$rg"

  # AI Foundry
  AI_FOUNDRY_NAME=$(az cognitiveservices account list -g "$rg" \
    --query "[?kind=='AIServices'].name | [0]" -o tsv 2>/dev/null || true)
  if [[ -n "$AI_FOUNDRY_NAME" ]]; then
    AI_FOUNDRY_ENDPOINT="https://${AI_FOUNDRY_NAME}.cognitiveservices.azure.com/"
    set_config AI_FOUNDRY_NAME "$AI_FOUNDRY_NAME"
    set_config AI_FOUNDRY_ENDPOINT "$AI_FOUNDRY_ENDPOINT"
    ok "AI Foundry:   $AI_FOUNDRY_NAME"
  fi

  # AI Foundry project
  AI_FOUNDRY_PROJECT_NAME=$(az cognitiveservices account list -g "$rg" \
    --query "[?kind=='AIServices' && contains(name,'proj')].name | [0]" -o tsv 2>/dev/null || true)
  if [[ -z "$AI_FOUNDRY_PROJECT_NAME" && -n "$AI_FOUNDRY_NAME" ]]; then
    local suffix="${AI_FOUNDRY_NAME#aif-}"
    AI_FOUNDRY_PROJECT_NAME="proj-${suffix}"
  fi
  [[ -n "$AI_FOUNDRY_PROJECT_NAME" ]] && set_config AI_FOUNDRY_PROJECT_NAME "$AI_FOUNDRY_PROJECT_NAME"

  if [[ -n "$AI_FOUNDRY_NAME" && -n "$AI_FOUNDRY_PROJECT_NAME" ]]; then
    PROJECT_ENDPOINT="https://${AI_FOUNDRY_NAME}.services.ai.azure.com/api/projects/${AI_FOUNDRY_PROJECT_NAME}"
    set_config PROJECT_ENDPOINT "$PROJECT_ENDPOINT"
    ok "Project EP:   $PROJECT_ENDPOINT"
  fi

  # AI Search
  AI_SEARCH_NAME=$(az search service list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$AI_SEARCH_NAME" ]] && { set_config AI_SEARCH_NAME "$AI_SEARCH_NAME"; ok "AI Search:    $AI_SEARCH_NAME"; }

  # Storage Account
  STORAGE_ACCOUNT_NAME=$(az storage account list -g "$rg" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$STORAGE_ACCOUNT_NAME" ]] && { set_config STORAGE_ACCOUNT_NAME "$STORAGE_ACCOUNT_NAME"; ok "Storage:      $STORAGE_ACCOUNT_NAME"; }

  # Key Vault
  KEY_VAULT_NAME=$(az keyvault list -g "$rg" --query "[0].name" -o tsv 2>/dev/null || true)
  if [[ -n "$KEY_VAULT_NAME" ]]; then
    KEY_VAULT_URI=$(az keyvault show -g "$rg" -n "$KEY_VAULT_NAME" --query properties.vaultUri -o tsv 2>/dev/null || true)
    set_config KEY_VAULT_NAME "$KEY_VAULT_NAME"
    [[ -n "$KEY_VAULT_URI" ]] && set_config KEY_VAULT_URI "$KEY_VAULT_URI"
    ok "Key Vault:    $KEY_VAULT_NAME"
  fi

  # Publish Job
  PUBLISH_JOB_NAME=$(az containerapp job list -g "$rg" --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$PUBLISH_JOB_NAME" ]] && { set_config PUBLISH_JOB_NAME "$PUBLISH_JOB_NAME"; ok "Publish Job:  $PUBLISH_JOB_NAME"; }

  # Cosmos DB Gremlin account
  COSMOS_GREMLIN_ACCOUNT_NAME=$(az cosmosdb list -g "$rg" \
    --query "[?kind=='GlobalDocumentDB' && contains(capabilities[].name, 'EnableGremlin')].name | [0]" -o tsv 2>/dev/null || true)
  if [[ -n "$COSMOS_GREMLIN_ACCOUNT_NAME" ]]; then
    COSMOS_GREMLIN_ENDPOINT=$(az cosmosdb show -g "$rg" -n "$COSMOS_GREMLIN_ACCOUNT_NAME" --query documentEndpoint -o tsv 2>/dev/null || true)
    COSMOS_GREMLIN_DATABASE=$(az cosmosdb gremlin database list -g "$rg" -a "$COSMOS_GREMLIN_ACCOUNT_NAME" --query "[0].name" -o tsv 2>/dev/null || true)
    if [[ -n "$COSMOS_GREMLIN_DATABASE" ]]; then
      COSMOS_GREMLIN_GRAPH=$(az cosmosdb gremlin graph list -g "$rg" -a "$COSMOS_GREMLIN_ACCOUNT_NAME" -d "$COSMOS_GREMLIN_DATABASE" --query "[0].name" -o tsv 2>/dev/null || true)
    else
      COSMOS_GREMLIN_GRAPH=""
    fi

    set_config COSMOS_GREMLIN_ACCOUNT_NAME "$COSMOS_GREMLIN_ACCOUNT_NAME"
    [[ -n "$COSMOS_GREMLIN_ENDPOINT" ]] && set_config COSMOS_GREMLIN_ENDPOINT "$COSMOS_GREMLIN_ENDPOINT"
    [[ -n "$COSMOS_GREMLIN_DATABASE" ]] && set_config COSMOS_GREMLIN_DATABASE "$COSMOS_GREMLIN_DATABASE"
    [[ -n "$COSMOS_GREMLIN_GRAPH" ]] && set_config COSMOS_GREMLIN_GRAPH "$COSMOS_GREMLIN_GRAPH"
    ok "Cosmos Graph: $COSMOS_GREMLIN_ACCOUNT_NAME"
  fi

  ok "Auto-discovery complete"
}

# ── Step 0: Prerequisites ──────────────────────────────────────────

banner

step "Step 0: Checking & installing prerequisites"

# ── Auto-install helpers ────────────────────────────────────────────

install_python3() {
  info "Installing Python 3..."
  if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-venv python3-pip >/dev/null
  elif command -v dnf &>/dev/null; then
    sudo dnf install -y python3 >/dev/null
  elif command -v brew &>/dev/null; then
    brew install python@3.12
  else
    fail "Cannot auto-install Python 3 — unknown package manager."
    return 1
  fi
}

install_uv() {
  info "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
}

install_az() {
  info "Installing Azure CLI..."
  curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
}

install_azd() {
  info "Installing Azure Developer CLI..."
  curl -fsSL https://aka.ms/install-azd.sh | bash
  export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"
}

# ── Check each prerequisite ────────────────────────────────────────

PREREQ_OK=true

ensure_cmd() {
  local cmd="$1" friendly="$2" installer="$3"
  if command -v "$cmd" &>/dev/null; then
    ok "$friendly: $(command -v "$cmd")"
    return 0
  fi

  warn "$friendly not found."
  if $AUTO_YES || confirm "Install $friendly now?"; then
    if $installer; then
      if command -v "$cmd" &>/dev/null; then
        ok "$friendly installed: $(command -v "$cmd")"
        return 0
      fi
      hash -r 2>/dev/null
      if command -v "$cmd" &>/dev/null; then
        ok "$friendly installed: $(command -v "$cmd")"
        return 0
      fi
    fi
    fail "$friendly installation failed."
    PREREQ_OK=false
  else
    fail "$friendly is required. Skipping."
    PREREQ_OK=false
  fi
}

ensure_cmd python3 "Python 3.11+" install_python3
ensure_cmd uv      "uv"           install_uv
ensure_cmd az      "Azure CLI"    install_az
ensure_cmd azd     "Azure Developer CLI" install_azd

# Verify Python version is 3.11+
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
    fail "Python $PY_VER found but 3.11+ is required."
    PREREQ_OK=false
  fi
fi

if ! $PREREQ_OK; then
  fail "Missing prerequisites. Install them and re-run."
  exit 1
fi

# Verify az login
if ! az account show &>/dev/null; then
  warn "Not logged in to Azure CLI."
  info "Running: az login"
  az login
fi
ok "Azure CLI authenticated: $(az account show --query name -o tsv)"

# Verify azd login
if ! azd auth login --check-status &>/dev/null 2>&1; then
  warn "Not logged in to azd."
  info "Running: azd auth login"
  azd auth login
fi
ok "azd authenticated"

# ── Step 1: Environment selection ───────────────────────────────────

step "Step 1: Azure environment selection"

EXISTING_ENVS=$(azd env list --output json 2>/dev/null || echo "[]")
ENV_COUNT=$(echo "$EXISTING_ENVS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [[ -n "$AZD_ENV_NAME" ]]; then
  info "Using environment from --env flag: $AZD_ENV_NAME"
  USE_ENV="$AZD_ENV_NAME"

elif (( ENV_COUNT > 0 )); then
  echo ""
  info "Found existing azd environment(s):"
  azd env list 2>/dev/null
  echo ""

  DEFAULT_ENV=$(echo "$EXISTING_ENVS" | python3 -c "
import sys, json
envs = json.load(sys.stdin)
default = [e for e in envs if e.get('IsDefault')]
print(default[0]['Name'] if default else envs[0]['Name'])
" 2>/dev/null || echo "")

  if $AUTO_YES; then
    USE_ENV="$DEFAULT_ENV"
    info "Auto-selecting default environment: $USE_ENV"
  else
    choose "What would you like to do?" \
      "Use existing environment: $DEFAULT_ENV" \
      "Delete existing and create new environment" \
      "Create a new separate environment"

    case "$CHOSEN" in
      "Use existing"*)
        USE_ENV="$DEFAULT_ENV"
        ;;
      "Delete existing"*)
        warn "This will destroy all Azure resources in '$DEFAULT_ENV'."
        if confirm "Are you sure?"; then
          info "Tearing down '$DEFAULT_ENV'..."
          azd env select "$DEFAULT_ENV" 2>/dev/null || true
          azd down --force --purge 2>&1 | tail -5 || true
          azd env delete "$DEFAULT_ENV" --yes 2>/dev/null || true
          ok "Old environment deleted."
        else
          info "Aborted."
          exit 0
        fi
        echo -en "${YELLOW}?${NC}  New environment name: "
        read -r USE_ENV
        ;;
      "Create a new"*)
        echo -en "${YELLOW}?${NC}  New environment name: "
        read -r USE_ENV
        ;;
    esac
  fi
else
  if $AUTO_YES; then
    USE_ENV="graph-data"
    info "No existing environments. Creating: $USE_ENV"
  else
    echo -en "${YELLOW}?${NC}  No existing environments. Enter a name for the new environment: "
    read -r USE_ENV
  fi
fi

if [[ -z "$USE_ENV" ]]; then
  fail "Environment name cannot be empty."
  exit 1
fi

if azd env list 2>/dev/null | grep -q "$USE_ENV"; then
  azd env select "$USE_ENV"
  ok "Selected existing environment: $USE_ENV"
else
  azd env new "$USE_ENV"
  ok "Created new environment: $USE_ENV"
fi

# ── Step 2: Configure azure_config.env ──────────────────────────────

step "Step 2: Configuring environment"

declare -A _PREV_VALS
if [[ -f "$CONFIG_FILE" ]]; then
  info "Preserving existing config values..."
  while IFS='=' read -r key val; do
    [[ -z "$key" || "$key" =~ ^# ]] && continue
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    if [[ -n "$val" ]]; then
      _PREV_VALS["$key"]="$val"
    fi
  done < <(grep -E '^[A-Z_]+=' "$CONFIG_FILE" 2>/dev/null || true)
  info "  Preserved ${#_PREV_VALS[@]} values from existing config"
fi

info "Creating azure_config.env from template..."
cp "$CONFIG_TEMPLATE" "$CONFIG_FILE"
ok "Copied template → azure_config.env"

for key in "${!_PREV_VALS[@]}"; do
  set_config "$key" "${_PREV_VALS[$key]}"
done
unset _PREV_VALS

# Determine location
if [[ -z "$AZURE_LOC" ]]; then
  AZURE_LOC=$(azd env get-values 2>/dev/null | grep "^AZURE_LOCATION=" | cut -d'"' -f2 || echo "")
  if [[ -z "$AZURE_LOC" ]]; then
    AZURE_LOC="swedencentral"
  fi
  if ! $AUTO_YES; then
    echo -en "${YELLOW}?${NC}  Azure location [${AZURE_LOC}]: "
    read -r loc_input
    if [[ -n "$loc_input" ]]; then AZURE_LOC="$loc_input"; fi
  fi
fi
info "Location: $AZURE_LOC"

set_config AZURE_LOCATION "$AZURE_LOC"
ok "Location: $AZURE_LOC"

# ── Step 3: Deploy infrastructure ───────────────────────────────────

if $SKIP_INFRA; then
  step "Step 3: Infrastructure provisioning (SKIPPED)"
  info "Using existing Azure resources."
else
  step "Step 3: Provisioning Azure infrastructure"

  info "This will provision:"
  echo "   • Resource Group"
  echo "   • AI Foundry (account + project + embedding model)"
  echo "   • Azure AI Search"
  echo "   • Storage Account"
  echo ""

  if ! $AUTO_YES; then
    if ! confirm "Proceed with infrastructure deployment?"; then
      info "Skipping infrastructure. Re-run with --skip-infra to use existing."
      exit 0
    fi
  fi

  azd env set AZURE_LOCATION "$AZURE_LOC"
  azd env set GPT_CAPACITY_1K_TPM "${GPT_CAPACITY_1K_TPM:-300}"

  info "Running azd provision (this may take 5-10 minutes)..."
  echo ""

  if ! azd provision; then
    fail "azd provision failed. Check the output above for errors."
    fail "Common issues:"
    echo "   • Quota exceeded — try a different location"
    echo "   • Soft-deleted resources — run: azd down --purge, then retry"
    echo "   • Name conflict — use a different --env name"
    exit 1
  fi

  ok "Infrastructure provisioned!"

  if [[ -f "$CONFIG_FILE" ]]; then
    set -a; source "$CONFIG_FILE"; set +a
  fi
fi

# ── Step 3b: Auto-discover / verify resource config ─────────────────

step "Step 3b: Verifying & discovering Azure resource configuration"

RG="${AZURE_RESOURCE_GROUP:-}"
if [[ -z "$RG" ]]; then
  AZD_ENV=$(azd env get-values 2>/dev/null | grep "^AZURE_ENV_NAME=" | cut -d'"' -f2 || true)
  if [[ -n "$AZD_ENV" ]]; then
    RG="rg-${AZD_ENV}"
  fi
fi

if [[ -z "$RG" ]]; then
  fail "Cannot determine resource group. Set AZURE_RESOURCE_GROUP or ensure azd env is configured."
  exit 1
fi

AZURE_RESOURCE_GROUP="$RG"

if [[ -z "${AI_FOUNDRY_NAME:-}" || -z "${AI_SEARCH_NAME:-}" || -z "${STORAGE_ACCOUNT_NAME:-}" ]]; then
  info "One or more resource values missing — running auto-discovery from $RG..."
  discover_resources_from_rg "$RG"
else
  ok "All critical config values already present"
fi

set -a; source "$CONFIG_FILE"; set +a
ok "azure_config.env is up to date"

MISSING_VARS=()
[[ -z "${AI_FOUNDRY_NAME:-}" ]]       && MISSING_VARS+=("AI_FOUNDRY_NAME")
[[ -z "${AI_SEARCH_NAME:-}" ]]        && MISSING_VARS+=("AI_SEARCH_NAME")
[[ -z "${STORAGE_ACCOUNT_NAME:-}" ]]  && MISSING_VARS+=("STORAGE_ACCOUNT_NAME")

if (( ${#MISSING_VARS[@]} > 0 )); then
  warn "These values are still missing after discovery:"
  for v in "${MISSING_VARS[@]}"; do echo "   • $v"; done
  warn "Resources may not exist yet. Run without --skip-infra to provision them."
else
  ok "All critical config values populated"
fi

# ── Step 5b: App Infrastructure (optional) ──────────────────────────
# Deploys Container App infra (ACR, CAE, identity, RBAC) into the
# existing resource group WITHOUT touching data resources.

if $DEPLOY_APP_INFRA; then
  step "Step 5b: Deploying Container App infrastructure"

  if [[ -f "$CONFIG_FILE" ]]; then
    set -a; source "$CONFIG_FILE"; set +a
  fi

  RG="${AZURE_RESOURCE_GROUP:-}"
  if [[ -z "$RG" ]]; then
    fail "AZURE_RESOURCE_GROUP not set. Run azd provision first or set it in azure_config.env."
    exit 1
  fi

  # Verify required resource names exist (from prior infrastructure provisioning)
  for var in AI_FOUNDRY_NAME AI_SEARCH_NAME STORAGE_ACCOUNT_NAME; do
    if [[ -z "${!var:-}" ]]; then
      fail "$var not set. Provision data infrastructure first (azd provision)."
      exit 1
    fi
  done

  # Resolve azd environment name for Bicep resource token consistency
  APP_INFRA_ENV="${AZD_ENV_NAME:-}"
  if [[ -z "$APP_INFRA_ENV" ]]; then
    APP_INFRA_ENV=$(azd env get-values 2>/dev/null | grep "^AZURE_ENV_NAME=" | cut -d'"' -f2 || true)
  fi
  if [[ -z "$APP_INFRA_ENV" ]]; then
    fail "Cannot determine azd environment name. Use --env <name>."
    exit 1
  fi

  info "Deploying Container App infra into RG: $RG"
  info "  AI Foundry:  ${AI_FOUNDRY_NAME}"
  info "  AI Search:   ${AI_SEARCH_NAME}"
  info "  Storage:     ${STORAGE_ACCOUNT_NAME}"

  # Export env vars for Bicep parameter file (app-main.bicepparam reads these)
  export AZURE_ENV_NAME="$APP_INFRA_ENV"
  export AZURE_LOCATION="${AZURE_LOC:-${AZURE_LOCATION:-swedencentral}}"
  export AI_FOUNDRY_NAME="${AI_FOUNDRY_NAME}"
  export AI_SEARCH_NAME="${AI_SEARCH_NAME}"
  export STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME}"
  export PROJECT_ENDPOINT="${PROJECT_ENDPOINT:-}"
  export CHAT_MODEL_DEPLOYMENT="${CHAT_MODEL_DEPLOYMENT:-gpt-4.1}"
  export CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-graph-demo}"

  # Build Azure Portal URL for monitoring the deployment in real time
  _sub="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv 2>/dev/null)}"
  _deploy_id="/subscriptions/${_sub}/resourceGroups/${RG}/providers/Microsoft.Resources/deployments/app-main"
  _portal_url="https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/overview/id/$(python3 -c "import urllib.parse; print(urllib.parse.quote('${_deploy_id}', safe=''))")"

  info "Running az deployment group create (this may take 3-5 minutes)..."
  info "Monitor in Azure Portal:"
  echo -e "   ${CYAN}${_portal_url}${NC}"
  echo ""

  # Deploy infrastructure resources (identity, CAE, ACR, container app)
  # Bicep uses upsert semantics — safe to re-run.
  # RBAC is handled separately below via `az role assignment create` (idempotent).
  DEPLOY_EXIT=0
  az deployment group create \
    --resource-group "$RG" \
    --template-file "$(_az_path "$PROJECT_ROOT/infra/app-main.bicep")" \
    --parameters "$(_az_path "$PROJECT_ROOT/infra/app-main.bicepparam")" \
    --verbose \
    -o table 2>&1 || DEPLOY_EXIT=$?

  if (( DEPLOY_EXIT != 0 )); then
    fail "Container App infrastructure deployment failed."
    fail "Run 'az deployment group show -g $RG -n app-main' for details."
    exit 1
  fi

  echo ""
  ok "Container App infrastructure deployed!"

  # Discover deployed resources and save to azure_config.env
  info "Discovering deployed Container App resources..."

  # Container Apps Environment
  _cae_name=$(az containerapp env list -g "$RG" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  [[ -n "$_cae_name" ]] && { set_config CONTAINER_APPS_ENV_NAME "$_cae_name"; ok "  CAE: $_cae_name"; }

  # ACR
  _acr_name=$(az acr list -g "$RG" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  _acr_login=$(az acr list -g "$RG" \
    --query "[0].loginServer" -o tsv 2>/dev/null || true)
  [[ -n "$_acr_name" ]] && { set_config ACR_NAME "$_acr_name"; ok "  ACR: $_acr_name"; }
  [[ -n "$_acr_login" ]] && set_config ACR_LOGIN_SERVER "$_acr_login"

  # Container App URL
  _app_fqdn=$(az containerapp show \
    --name "${CONTAINER_APP_NAME:-graph-demo}" \
    --resource-group "$RG" \
    --query "properties.configuration.ingress.fqdn" \
    -o tsv 2>/dev/null || true)
  if [[ -n "$_app_fqdn" ]]; then
    _app_url="https://${_app_fqdn}"
    set_config APP_URL "$_app_url"
    ok "  App URL: $_app_url"
  fi

  # Managed identity
  _id_name=$(az identity list -g "$RG" \
    --query "[0].name" -o tsv 2>/dev/null || true)
  _id_resource=$(az identity list -g "$RG" \
    --query "[0].id" -o tsv 2>/dev/null || true)
  _id_client=$(az identity list -g "$RG" \
    --query "[0].clientId" -o tsv 2>/dev/null || true)
  _id_principal=$(az identity list -g "$RG" \
    --query "[0].principalId" -o tsv 2>/dev/null || true)
  [[ -n "$_id_resource" ]] && set_config APP_IDENTITY_ID "$_id_resource"
  [[ -n "$_id_client" ]] && { set_config APP_IDENTITY_CLIENT_ID "$_id_client"; ok "  Identity: $_id_name ($_id_client)"; }

  # Deployment outputs that are easiest to resolve from the ARM deployment itself
  _deployment_outputs=$(az deployment group show \
    --resource-group "$RG" \
    --name app-main \
    --query properties.outputs \
    -o json 2>/dev/null || echo '{}')

  _output_value() {
    local key="$1"
    printf '%s' "$_deployment_outputs" | python3 "$SCRIPT_DIR/scripts/deployment_outputs.py" --key "$key" 2>/dev/null || true
  }

  _publish_job_name=$(_output_value PUBLISH_JOB_NAME)
  _key_vault_name=$(_output_value KEY_VAULT_NAME)
  _key_vault_uri=$(_output_value KEY_VAULT_URI)
  _cosmos_gremlin_endpoint=$(_output_value COSMOS_GREMLIN_ENDPOINT)
  _cosmos_gremlin_account=$(_output_value COSMOS_GREMLIN_ACCOUNT)
  _cosmos_gremlin_database=$(_output_value COSMOS_GREMLIN_DATABASE)
  _cosmos_gremlin_graph=$(_output_value COSMOS_GREMLIN_GRAPH)
  _cosmos_telemetry_database=$(_output_value COSMOS_TELEMETRY_DATABASE)

  [[ -n "$_publish_job_name" ]] && { set_config PUBLISH_JOB_NAME "$_publish_job_name"; ok "  Publish Job: $_publish_job_name"; }
  [[ -n "$_key_vault_name" ]] && { set_config KEY_VAULT_NAME "$_key_vault_name"; ok "  Key Vault: $_key_vault_name"; }
  [[ -n "$_key_vault_uri" ]] && set_config KEY_VAULT_URI "$_key_vault_uri"
  [[ -n "$_cosmos_gremlin_endpoint" ]] && set_config COSMOS_GREMLIN_ENDPOINT "$_cosmos_gremlin_endpoint"
  [[ -n "$_cosmos_gremlin_account" ]] && set_config COSMOS_GREMLIN_ACCOUNT_NAME "$_cosmos_gremlin_account"
  [[ -n "$_cosmos_gremlin_database" ]] && set_config COSMOS_GREMLIN_DATABASE "$_cosmos_gremlin_database"
  [[ -n "$_cosmos_gremlin_graph" ]] && set_config COSMOS_GREMLIN_GRAPH "$_cosmos_gremlin_graph"
  [[ -n "$_cosmos_telemetry_database" ]] && set_config COSMOS_TELEMETRY_DATABASE "$_cosmos_telemetry_database"

  ok "Container App config saved to azure_config.env"

  # ── RBAC: assign roles to managed identity ─────────────────────────
  # Using `az role assignment create` which is naturally idempotent —
  # it succeeds silently if the assignment already exists.
  if [[ -n "$_id_principal" ]]; then
    info "Assigning RBAC roles to managed identity..."

    _assign_role() {
      local role_name="$1" scope="$2"
      az role assignment create \
        --assignee-object-id "$_id_principal" \
        --assignee-principal-type ServicePrincipal \
        --role "$role_name" \
        --scope "$scope" \
        -o none 2>/dev/null && ok "  $role_name → $(basename "$scope")" \
        || warn "  Failed: $role_name → $(basename "$scope")"
    }

    # Resolve resource IDs for RBAC scoping
    _foundry_id=$(az cognitiveservices account show -n "${AI_FOUNDRY_NAME}" -g "$RG" --query id -o tsv 2>/dev/null || true)
    _search_id=$(az search service show -n "${AI_SEARCH_NAME}" -g "$RG" --query id -o tsv 2>/dev/null || true)
    _storage_id=$(az storage account show -n "${STORAGE_ACCOUNT_NAME}" -g "$RG" --query id -o tsv 2>/dev/null || true)
    _rg_id=$(az group show -n "$RG" --query id -o tsv 2>/dev/null || true)

    # AI Foundry: invoke models + manage resource
    [[ -n "$_foundry_id" ]] && _assign_role "Cognitive Services OpenAI User" "$_foundry_id"
    [[ -n "$_foundry_id" ]] && _assign_role "Cognitive Services Contributor" "$_foundry_id"
    # Cognitive Services User: broad data-plane access including AIServices/agents/*
    [[ -n "$_foundry_id" ]] && _assign_role "Cognitive Services User" "$_foundry_id"
    # Azure AI Developer at RG scope: grants MachineLearningServices/workspaces/agents/*
    # (the Foundry project is backed by an AML workspace — agents/action lives there)
    [[ -n "$_rg_id" ]] && _assign_role "Azure AI Developer" "$_rg_id"

    # AI Search: query runbooks + tickets indexes
    [[ -n "$_search_id" ]] && _assign_role "Search Index Data Contributor" "$_search_id"
    [[ -n "$_search_id" ]] && _assign_role "Search Service Contributor" "$_search_id"

    # Storage: read/write package and report blobs
    [[ -n "$_storage_id" ]] && _assign_role "Storage Blob Data Reader" "$_storage_id"
    [[ -n "$_storage_id" ]] && _assign_role "Storage Blob Data Contributor" "$_storage_id"

    ok "Azure RBAC assignments complete"

    # ── Cosmos DB RBAC: data-plane access for session persistence ──────
    # Cosmos DB data-plane RBAC is SEPARATE from Azure ARM RBAC.
    # `az role assignment create` gives ARM access (list accounts, read keys)
    # but NOT data-plane access (read/write documents).
    # Must use `az cosmosdb sql role assignment create` with the built-in
    # role definition ID 00000000-0000-0000-0000-000000000002 (Data Contributor).
    # Filter by EnableServerless capability to avoid matching the existing
    # Cosmos Gremlin account.
    _cosmos_name=$(az cosmosdb list -g "$RG" \
      --query "[?starts_with(name, 'cosmos-') && contains(capabilities[].name, 'EnableServerless')].name | [0]" -o tsv 2>/dev/null || true)

    if [[ -n "$_cosmos_name" ]]; then
      info "Assigning Cosmos DB data-plane RBAC..."

      # Container App managed identity → Cosmos DB Built-in Data Contributor
      az cosmosdb sql role assignment create \
        --account-name "$_cosmos_name" \
        --resource-group "$RG" \
        --role-definition-id "00000000-0000-0000-0000-000000000002" \
        --principal-id "$_id_principal" \
        --scope "/" \
        -o none 2>/dev/null \
        && ok "  Cosmos DB Data Contributor → app identity" \
        || warn "  Cosmos DB app role assignment failed (may already exist)"

      # Signed-in user → Cosmos DB Built-in Data Contributor (for local dev)
      _user_oid=$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)
      if [[ -n "$_user_oid" ]]; then
        az cosmosdb sql role assignment create \
          --account-name "$_cosmos_name" \
          --resource-group "$RG" \
          --role-definition-id "00000000-0000-0000-0000-000000000002" \
          --principal-id "$_user_oid" \
          --scope "/" \
          -o none 2>/dev/null \
          && ok "  Cosmos DB Data Contributor → user" \
          || warn "  Cosmos DB user role assignment failed (may already exist)"
      fi

      # Discover endpoint and persist to azure_config.env
      _cosmos_endpoint=$(az cosmosdb show -n "$_cosmos_name" -g "$RG" \
        --query documentEndpoint -o tsv 2>/dev/null || true)
      [[ -n "$_cosmos_endpoint" ]] && set_config COSMOS_SESSION_ENDPOINT "$_cosmos_endpoint"

      ok "Cosmos DB session store configured"
    else
      info "No Cosmos DB serverless account found — session store will use in-memory (dev mode)"
    fi
  else
    warn "Could not determine identity principal ID — skipping RBAC."
    warn "Assign roles manually after deployment."
  fi
else
  if ! $SKIP_INFRA; then
    : # Don't print skip message when doing other things
  else
    step "Step 5b: Container App Infrastructure (SKIPPED — use --app-infra)"
  fi
fi

# ── Step 6: Sync azure_config.env → control/.env ───────────────────
# Merges provisioned resource IDs into control/.env for local dev (dev.sh).
# In production, the ConfigResolver discovers values from Azure directly —
# this sync is only needed for local development without the resolver.
# Only overwrites keys that have non-empty values in azure_config.env,
# so manual control/.env settings (LLM_PROVIDER, etc.)
# are preserved.

CONTROL_ENV="$(cd "$PROJECT_ROOT/.." && pwd)/control/.env"

if [[ -f "$CONFIG_FILE" && -f "$CONTROL_ENV" ]]; then
  step "Step 6: Syncing azure_config.env → control/.env"

  # Source azure_config.env to get the latest provisioned values
  set -a; source "$CONFIG_FILE"; set +a

  # Map azure_config.env vars → control/.env var names.
  # Only update if the source value is non-empty.
  declare -A SYNC_MAPPINGS=(
    [AZURE_AI_PROJECT_ENDPOINT]="${PROJECT_ENDPOINT:-}"
    [AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME]="${CHAT_MODEL_DEPLOYMENT:-}"
    [COSMOS_SESSION_ENDPOINT]="${COSMOS_SESSION_ENDPOINT:-}"
    [COSMOS_GREMLIN_ENDPOINT]="${COSMOS_GREMLIN_ENDPOINT:-}"
    [COSMOS_GREMLIN_ACCOUNT_NAME]="${COSMOS_GREMLIN_ACCOUNT_NAME:-}"
    [COSMOS_GREMLIN_DATABASE]="${COSMOS_GREMLIN_DATABASE:-}"
    [COSMOS_GREMLIN_GRAPH]="${COSMOS_GREMLIN_GRAPH:-}"
    [COSMOS_TELEMETRY_DATABASE]="${COSMOS_TELEMETRY_DATABASE:-}"
  )

  # Derive AI_SEARCH_ENDPOINT from AI_SEARCH_NAME if available
  if [[ -n "${AI_SEARCH_NAME:-}" ]]; then
    SYNC_MAPPINGS[AI_SEARCH_ENDPOINT]="https://${AI_SEARCH_NAME}.search.windows.net"
  fi

  _synced=0
  for key in "${!SYNC_MAPPINGS[@]}"; do
    val="${SYNC_MAPPINGS[$key]}"
    [[ -z "$val" ]] && continue   # Skip empty — don't overwrite with blanks
    if grep -q "^${key}=" "$CONTROL_ENV" 2>/dev/null; then
      old_val=$(grep "^${key}=" "$CONTROL_ENV" | head -1 | cut -d= -f2-)
      if [[ "$old_val" != "$val" ]]; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$CONTROL_ENV"
        info "  Updated $key"
        ((++_synced))
      fi
    else
      echo "${key}=${val}" >> "$CONTROL_ENV"
      info "  Added $key"
      ((++_synced))
    fi
  done

  if (( _synced > 0 )); then
    ok "Synced $_synced value(s) into control/.env"
  else
    ok "control/.env already up to date"
  fi
else
  if [[ ! -f "$CONTROL_ENV" ]]; then
    info "Skipping control/.env sync — file does not exist yet (run dev.sh to initialise)"
  fi
fi

# ── Summary ─────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete!                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "  ${BOLD}Environment:${NC}      $USE_ENV"
echo -e "  ${BOLD}Location:${NC}         ${AZURE_LOC}"
echo -e "  ${BOLD}Resource Group:${NC}   ${AZURE_RESOURCE_GROUP:-<pending>}"
echo ""
echo -e "  ${BOLD}Azure Services:${NC}"
echo "    AI Foundry:       ${AI_FOUNDRY_NAME:-<pending>}"
echo "    AI Search:        ${AI_SEARCH_NAME:-<pending>}"
echo "    Storage:          ${STORAGE_ACCOUNT_NAME:-<pending>}"
echo ""

echo -e "  ${BOLD}Useful commands:${NC}"
echo "    azd down --force --purge            # Tear down all Azure resources"
echo ""
echo -e "  ${BOLD}Provisioning:${NC}"
echo "    ./deploy_infra.sh --app-infra       # Deploy Container App infra (ACR, CAE, identity)"
echo ""
