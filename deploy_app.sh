#!/usr/bin/env bash
# ============================================================================
# deploy_app.sh — Build and deploy the unified container to Azure Container Apps
# ============================================================================
#
# This script handles APPLICATION deployment only (no infrastructure).
# Prerequisites:
#   - Azure Container App infrastructure already provisioned
#     (run: cd graph_data && ./deploy.sh --app-infra)
#   - azure_config.env populated with ACR_NAME, ACR_LOGIN_SERVER,
#     CONTAINER_APPS_ENV_NAME, APP_IDENTITY_CLIENT_ID, etc.
#
# Pipeline:
#   1. Load config from graph_data/azure_config.env + control/.env
#   2. Build unified Docker image (frontend + backend + scenario data)
#   3. Push image to Azure Container Registry (ACR)
#   4. Update the Container App with the new image + environment variables
#   5. Verify health endpoint
#
# Options:
#   --build-only         Build and push the image but don't update the Container App
#   --update-only        Update the Container App without rebuilding the image
#   --tag TAG            Docker image tag (default: latest)
#   --app-name NAME      Container App name (default: graph-demo)
#   --yes                Skip confirmation prompts
#   --help               Show this help
#
# Usage:
#   chmod +x deploy_app.sh && ./deploy_app.sh
#   ./deploy_app.sh --tag v1.2.3
#   ./deploy_app.sh --update-only
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
  echo "║  Graph Demo — App Deployment                                 ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

# ── Parse arguments ─────────────────────────────────────────────────

BUILD_ONLY=false
UPDATE_ONLY=false
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
CONTAINER_APP_NAME="graph-demo"
AUTO_YES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-only)   BUILD_ONLY=true; shift ;;
    --update-only)  UPDATE_ONLY=true; shift ;;
    --tag)          IMAGE_TAG="$2"; shift 2 ;;
    --app-name)     CONTAINER_APP_NAME="$2"; shift 2 ;;
    --yes|-y)       AUTO_YES=true; shift ;;
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

# ── Helper: prompt user ────────────────────────────────────────────

confirm() {
  local msg="$1"
  if $AUTO_YES; then return 0; fi
  echo -en "${YELLOW}?${NC}  ${msg} [y/N] "
  read -r answer
  [[ "$answer" =~ ^[Yy] ]]
}

# ── Step 0: Load configuration ─────────────────────────────────────

banner
step "Step 0: Loading configuration"

AZURE_CONFIG="$PROJECT_ROOT/graph_data/azure_config.env"
if [[ ! -f "$AZURE_CONFIG" ]]; then
  fail "azure_config.env not found at $AZURE_CONFIG"
  fail "Run: cd graph_data && ./deploy.sh  (to provision infra first)"
  exit 1
fi

# Source azure_config.env for all infra-provisioned values
set -a; source "$AZURE_CONFIG"; set +a

# Source control/.env for runtime config (scenario, auth, LLM settings).
# Values here override azure_config.env when both set the same var.
CONTROL_ENV="$PROJECT_ROOT/control/.env"
if [[ -f "$CONTROL_ENV" ]]; then
  set -a; source "$CONTROL_ENV"; set +a
fi

# Validate required variables from infrastructure provisioning
REQUIRED_VARS=(
  AZURE_RESOURCE_GROUP
  ACR_LOGIN_SERVER
  ACR_NAME
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    MISSING+=("$var")
  fi
done

if (( ${#MISSING[@]} > 0 )); then
  fail "Missing required config values:"
  for v in "${MISSING[@]}"; do echo "   • $v"; done
  fail ""
  fail "These are set by Container App infrastructure provisioning."
  fail "Run: cd graph_data && ./deploy.sh --skip-infra --app-infra"
  exit 1
fi

# Derive the full image name
IMAGE_NAME="${ACR_LOGIN_SERVER}/graph-demo:${IMAGE_TAG}"
PUBLISH_JOB_NAME="${PUBLISH_JOB_NAME:-}"
USE_KEY_VAULT_GREMLIN_SECRET=false
if [[ -n "${KEY_VAULT_URI:-}" ]]; then
  USE_KEY_VAULT_GREMLIN_SECRET=true
fi

ok "Configuration loaded"
info "Resource Group:   ${AZURE_RESOURCE_GROUP}"
info "ACR:              ${ACR_LOGIN_SERVER}"
info "Container App:    ${CONTAINER_APP_NAME}"
[[ -n "$PUBLISH_JOB_NAME" ]] && info "Publish Job:      ${PUBLISH_JOB_NAME}"
info "Image:            ${IMAGE_NAME}"

# ── Step 0.5: Clean Slate (optional) ───────────────────────────────
# Deactivate old revisions to force a fully clean restart.

if ! $BUILD_ONLY && ! $UPDATE_ONLY; then
  echo ""
  echo -e "${YELLOW}━━━ Clean Slate ━━━${NC}"
  echo -e "  Deactivate old revisions before deploying? The app will be"
  echo -e "  briefly unavailable. Ensures no cached state from prior revisions."
  echo ""
  echo -e "  ${BOLD}[Y]${NC} Yes — deactivate old revisions, deploy fresh"
  echo -e "  ${BOLD}[N]${NC} No  — deploy normally (default)"
  echo -e "  ${BOLD}[C]${NC} Cancel — abort deployment"
  echo ""

  if $AUTO_YES; then
    _clean_choice="n"
  else
    echo -en "${YELLOW}?${NC}  Choice [y/N/c]: "
    read -r _clean_choice
  fi

  case "$_clean_choice" in
    [Yy]*)
      step "Deactivating old revisions"
      _old_revisions=$(az containerapp revision list \
        -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
        --query "[?properties.active].name" -o tsv 2>/dev/null || true)
      for _rev in $_old_revisions; do
        info "  Deactivating $_rev"
        az containerapp revision deactivate \
          -n "$CONTAINER_APP_NAME" -g "$AZURE_RESOURCE_GROUP" \
          --revision "$_rev" -o none 2>/dev/null || true
      done
      ok "Old revisions deactivated — clean slate ready"
      ;;
    [Cc]*)
      info "Deployment cancelled."
      exit 0
      ;;
    *)
      info "Keeping existing revisions."
      ;;
  esac
fi

# ── Step 1: Prerequisites ──────────────────────────────────────────

step "Step 1: Checking prerequisites"

# Verify Azure CLI is authenticated
if ! az account show &>/dev/null; then
  fail "Not logged in to Azure CLI. Run: az login"
  exit 1
fi
ok "Azure CLI authenticated"

# ── Step 2: Build Docker image on ACR ──────────────────────────────

if ! $UPDATE_ONLY; then
  step "Step 2: Building image on ACR (remote build)"

  info "Build context: $PROJECT_ROOT"
  info "Dockerfile:    Dockerfile.unified"
  info "Image:         $IMAGE_NAME"
  info "ACR:           ${ACR_NAME}"
  echo ""
  info "The build runs on Azure Container Registry's build service."
  info "No local Docker installation required."

  if ! $AUTO_YES; then
    if ! confirm "Proceed with ACR remote build?"; then
      info "Aborted."
      exit 0
    fi
  fi

  # Clean node_modules before upload — it's rebuilt from scratch in the
  # Dockerfile Stage 1 (npm ci) and is never needed in the build context.
  # Azure CLI's tar packer does not reliably honour **/node_modules/ in
  # .dockerignore (glob matching regression in recent CLI versions), and
  # the massive directory tree causes ENOENT races on WSL2 filesystems.
  if [[ -d "$PROJECT_ROOT/app/frontend/node_modules" ]]; then
    info "Removing app/frontend/node_modules/ (rebuilt in Docker build stage)"
    rm -rf "$PROJECT_ROOT/app/frontend/node_modules"
  fi

  # az acr build: uploads the build context, builds on ACR, and pushes
  # the image to the registry in one step. No local Docker needed.
  if ! az acr build \
    --registry "${ACR_NAME}" \
    --image "graph-demo:${IMAGE_TAG}" \
    --file "$(_az_path "$PROJECT_ROOT/Dockerfile.unified")" \
    "$(_az_path "$PROJECT_ROOT")"; then
    fail "ACR remote build failed."
    exit 1
  fi

  ok "Image built and pushed: $IMAGE_NAME"

  if $BUILD_ONLY; then
    echo ""
    ok "Build complete (--build-only). Image is ready in ACR."
    echo "   To deploy: ./deploy_app.sh --update-only --tag $IMAGE_TAG"
    exit 0
  fi
else
  step "Step 2: Build & Push (SKIPPED — --update-only)"
  info "Using existing image: $IMAGE_NAME"
fi

# ── Step 3: Update Container App ───────────────────────────────────

step "Step 3: Updating Container App"

# 3a. Register the Fabric client secret in Container App secrets (Key Vault ref).
# The secret is stored in Key Vault and referenced by the container at runtime —
# never exposed as plaintext in environment variables or deployment history.
_KV_URI="${KEY_VAULT_URI:-}"
_MI_RID="${APP_IDENTITY_RESOURCE_ID:-}"
_USE_SECRET_REF=false
if [[ -n "$_KV_URI" && -n "$_MI_RID" ]]; then
  info "Registering Fabric client secret from Key Vault..."
  if az containerapp secret set \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --secrets "fabric-client-secret=keyvaultref:${_KV_URI}/secrets/FABRIC-CLIENT-SECRET,identityref:${_MI_RID}" \
    --output none 2>/dev/null; then
    _USE_SECRET_REF=true
  else
    warn "Could not set KV secret ref — falling back to env var"
  fi
else
  warn "KEY_VAULT_URI or APP_IDENTITY_RESOURCE_ID not set — Fabric secret passed as env var"
fi

# Build environment variable arguments for the container app update.
# Values come from azure_config.env (infra provisioning) and control/.env (runtime).

# Resolve AI Search endpoint from service name
_AI_SEARCH_ENDPOINT="${AI_SEARCH_ENDPOINT:-}"
if [[ -z "$_AI_SEARCH_ENDPOINT" && -n "${AI_SEARCH_NAME:-}" ]]; then
  _AI_SEARCH_ENDPOINT="https://${AI_SEARCH_NAME}.search.windows.net"
fi

# Model deployment name — control/.env value or azure_config.env fallback
_MODEL="${LLM_MODEL:-${CHAT_MODEL_DEPLOYMENT:-gpt-5.2}}"

info "Updating container image and environment variables..."

APP_ENV_VARS=(
  "LLM_PROVIDER=${LLM_PROVIDER:-agent}"
  "LLM_MODEL=${_MODEL}"
  "AZURE_AI_PROJECT_ENDPOINT=${PROJECT_ENDPOINT:-}"
  "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME=${_MODEL}"
  "AZURE_CLIENT_ID=${APP_IDENTITY_CLIENT_ID:-}"
  "FABRIC_API_URL=${FABRIC_API_URL:-https://api.fabric.microsoft.com/v1}"
  "FABRIC_SCOPE=${FABRIC_SCOPE:-https://api.fabric.microsoft.com/.default}"
  "FABRIC_TENANT_ID=${FABRIC_TENANT_ID:-}"
  "FABRIC_CLIENT_ID=${FABRIC_CLIENT_ID:-}"
)
# Conditionally pass Fabric secret as KV secretref or plaintext env var
if $_USE_SECRET_REF; then
  APP_ENV_VARS+=("FABRIC_CLIENT_SECRET=secretref:fabric-client-secret")
else
  APP_ENV_VARS+=("FABRIC_CLIENT_SECRET=${FABRIC_CLIENT_SECRET:-}")
fi
APP_ENV_VARS+=(
  "FABRIC_WORKSPACE_ID=${FABRIC_WORKSPACE_ID:-}"
  "FABRIC_GRAPH_MODEL_ID=${FABRIC_GRAPH_MODEL_ID:-}"
  "EVENTHOUSE_QUERY_URI=${EVENTHOUSE_QUERY_URI:-}"
  "FABRIC_KQL_DB_NAME=${FABRIC_KQL_DB_NAME:-}"
  "AI_SEARCH_ENDPOINT=${_AI_SEARCH_ENDPOINT}"
  "RUNBOOKS_INDEX_NAME=${RUNBOOKS_INDEX_NAME:-runbooks-index}"
  "TICKETS_INDEX_NAME=${TICKETS_INDEX_NAME:-tickets-index}"
  "EQUIPMENT_INDEX_NAME=${EQUIPMENT_INDEX_NAME:-telecom-playground-equipment-index}"
  "INFRA_SPECS_INDEX_NAME=${INFRA_SPECS_INDEX_NAME:-telecom-playground-infra-specs-index}"
  "SCENARIO_NAME=${SCENARIO_NAME:-${DEFAULT_SCENARIO:-}}"
  "AUTH_ENABLED=${AUTH_ENABLED:-true}"
  "AUTH_CLIENT_ID=${AUTH_CLIENT_ID:-}"
  "AUTH_TENANT_ID=${AUTH_TENANT_ID:-common}"
  "GRAPH_DATA_DIR=/workspace/graph_data"
  "CORS_ORIGINS=${CORS_ORIGINS:-[\"https://pathfinderiq.azureai.win\"]}"
  "DEBUG=false"
  "COSMOS_SESSION_ENDPOINT=${COSMOS_SESSION_ENDPOINT:-}"
)

# Capture the current revision before updating — used for rollback if the
# new revision fails health checks.
_PRE_DEPLOY_REV=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.latestReadyRevisionName" -o tsv 2>/dev/null || true)
[[ -n "$_PRE_DEPLOY_REV" ]] && info "Pre-deploy revision: $_PRE_DEPLOY_REV"

# Use 'az containerapp update' to set the new image and env vars.
# The --set-env-vars flag merges with existing vars (does not remove unset ones).
if ! az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --image "$IMAGE_NAME" \
  --set-env-vars "${APP_ENV_VARS[@]}" \
  --output none; then
  fail "Container App update failed."
  exit 1
fi

ok "Container App updated"

# Ensure ingress targets port 8080 (container runs as non-root, nginx on 8080)
az containerapp ingress update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --target-port 8080 \
  --output none 2>/dev/null || warn "Could not update ingress target port"

if [[ -n "$PUBLISH_JOB_NAME" ]]; then
  step "Step 3b: Updating publish job"

  JOB_ENV_VARS=(
    "AZURE_CLIENT_ID=${APP_IDENTITY_CLIENT_ID:-}"
    "AZURE_SUBSCRIPTION_ID=${AZURE_SUBSCRIPTION_ID:-}"
    "AZURE_RESOURCE_GROUP=${AZURE_RESOURCE_GROUP:-}"
    "GRAPH_DATA_DIR=/workspace/graph_data"
    "STORAGE_ACCOUNT_NAME=${STORAGE_ACCOUNT_NAME:-}"
    "STORAGE_PACKAGE_CONTAINER=${STORAGE_PACKAGE_CONTAINER:-scenario-packages}"
    "PACKAGE_BLOB_ROOT=${PACKAGE_BLOB_ROOT:-landing/scenarios}"
    "STORAGE_REPORTS_CONTAINER=${STORAGE_REPORTS_CONTAINER:-publish-reports}"
    "PUBLISH_REPORT_BLOB_ROOT=${PUBLISH_REPORT_BLOB_ROOT:-reports/publishes}"
    "AI_SEARCH_NAME=${AI_SEARCH_NAME:-}"
    "AI_FOUNDRY_NAME=${AI_FOUNDRY_NAME:-}"
    "PROJECT_ENDPOINT=${PROJECT_ENDPOINT:-}"
    "EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-small}"
    "EMBEDDING_DIMENSIONS=${EMBEDDING_DIMENSIONS:-1536}"
  )

  if ! az containerapp job update \
    --name "$PUBLISH_JOB_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --image "$IMAGE_NAME" \
    --set-env-vars "${JOB_ENV_VARS[@]}" \
    --output none; then
    fail "Publish job update failed."
    exit 1
  fi

  ok "Publish job updated"
else
  warn "PUBLISH_JOB_NAME not set — skipping publish job update."
fi

# Ensure the latest revision is active. When all prior revisions were
# deactivated (Clean Slate step), the new revision can sometimes start
# in an inactive state. Explicitly activating guarantees the container runs.
_LATEST_REV=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.latestRevisionName" -o tsv 2>/dev/null || true)

if [[ -n "$_LATEST_REV" ]]; then
  _REV_ACTIVE=$(az containerapp revision show \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --revision "$_LATEST_REV" \
    --query "properties.active" -o tsv 2>/dev/null || echo "false")

  if [[ "$_REV_ACTIVE" != "true" ]]; then
    info "Activating revision $_LATEST_REV (was inactive after update)"
    az containerapp revision activate \
      --name "$CONTAINER_APP_NAME" \
      --resource-group "$AZURE_RESOURCE_GROUP" \
      --revision "$_LATEST_REV" -o none 2>/dev/null || true
    ok "Revision $_LATEST_REV activated"
  else
    ok "Revision $_LATEST_REV is active"
  fi
fi

# Retrieve the app URL (may differ from what's in config if the app was just created)
APP_FQDN=$(az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" \
  -o tsv 2>/dev/null || true)

if [[ -n "$APP_FQDN" ]]; then
  APP_URL="https://${APP_FQDN}"
  ok "App URL: $APP_URL"
else
  APP_URL="${APP_URL:-<unknown>}"
  warn "Could not retrieve app URL from Azure."
fi

# ── Step 4: Health check ───────────────────────────────────────────

step "Step 4: Verifying deployment"

info "Waiting for container to start (checking $APP_URL/health/ready)..."

HEALTH_OK=false
for attempt in $(seq 1 12); do
  sleep 10
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$APP_URL/health/ready" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    HEALTH_OK=true
    break
  fi
  if (( attempt < 12 )); then
    warn "Attempt $attempt/12: HTTP $HTTP_CODE — waiting 10s..."
  fi
done

if $HEALTH_OK; then
  ok "App is healthy!"
else
  warn "Health check did not return 200 after 12 attempts."
  # Rollback to previous revision if available
  if [[ -n "${_PRE_DEPLOY_REV:-}" ]]; then
    warn "Rolling back to previous revision: $_PRE_DEPLOY_REV"
    az containerapp revision activate \
      --name "$CONTAINER_APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
      --revision "$_PRE_DEPLOY_REV" -o none 2>/dev/null || true
    # Deactivate the failed revision
    if [[ -n "${_LATEST_REV:-}" && "$_LATEST_REV" != "$_PRE_DEPLOY_REV" ]]; then
      az containerapp revision deactivate \
        --name "$CONTAINER_APP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
        --revision "$_LATEST_REV" -o none 2>/dev/null || true
    fi
    fail "Deployment rolled back to $_PRE_DEPLOY_REV"
  else
    info "No previous revision to roll back to. Check logs with:"
    echo "   az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $AZURE_RESOURCE_GROUP --follow"
  fi
fi

# ── Summary ─────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete!                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "  ${BOLD}Container App:${NC}     $CONTAINER_APP_NAME"
[[ -n "$PUBLISH_JOB_NAME" ]] && echo -e "  ${BOLD}Publish Job:${NC}       $PUBLISH_JOB_NAME"
echo -e "  ${BOLD}Image:${NC}             $IMAGE_NAME"
echo -e "  ${BOLD}App URL:${NC}           $APP_URL"
echo -e "  ${BOLD}Resource Group:${NC}    $AZURE_RESOURCE_GROUP"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo "    ./deploy_app.sh                         # Full rebuild + deploy"
echo "    ./deploy_app.sh --tag v2                 # Deploy with specific tag"
echo "    ./deploy_app.sh --update-only            # Update env vars only (no rebuild)"
echo "    ./deploy_app.sh --build-only             # Build + push to ACR (no deploy)"
echo ""
echo "    az containerapp logs show \\              # Stream container logs"
echo "      --name $CONTAINER_APP_NAME \\"
echo "      --resource-group $AZURE_RESOURCE_GROUP --follow"
echo ""
echo "    az containerapp revision list \\           # List deployment revisions"
echo "      --name $CONTAINER_APP_NAME \\"
echo "      --resource-group $AZURE_RESOURCE_GROUP -o table"
echo ""
