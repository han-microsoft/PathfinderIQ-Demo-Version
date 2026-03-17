#!/usr/bin/env bash
# ============================================================================
# Post-provision hook — populate azure_config.env with deployment outputs
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# azd populates outputs as env vars prefixed with AZURE_
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT_NAME:?Missing output AZURE_STORAGE_ACCOUNT_NAME}"
RG="${AZURE_RESOURCE_GROUP:?Missing output AZURE_RESOURCE_GROUP}"

echo "============================================"
echo "Post-provision: populating config"
echo "  Storage : $STORAGE_ACCOUNT"
echo "  RG      : $RG"
echo "============================================"

# --------------------------------------------------------------------------
# 1. Populate azure_config.env with deployment outputs
# --------------------------------------------------------------------------
echo ""
echo "Populating azure_config.env with deployment outputs..."

CONFIG_FILE="$PROJECT_ROOT/azure_config.env"

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
}

if [[ ! -f "$CONFIG_FILE" ]]; then
  TEMPLATE="$PROJECT_ROOT/azure_config.env.template"
  if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$CONFIG_FILE"
    echo "  ⚠ azure_config.env was missing — recreated from template"
  else
    echo "  ✗ Neither azure_config.env nor template found — cannot proceed"
    exit 1
  fi
fi

SUB_ID=$(az account show --query id -o tsv)

set -a; source "$CONFIG_FILE"; set +a

set_config AZURE_SUBSCRIPTION_ID "$SUB_ID"
set_config AZURE_RESOURCE_GROUP "$RG"
[[ -n "${AZURE_LOCATION:-}" ]] && set_config AZURE_LOCATION "$AZURE_LOCATION"

# AI Foundry
[[ -n "${AZURE_AI_FOUNDRY_NAME:-}" ]]        && set_config AI_FOUNDRY_NAME "$AZURE_AI_FOUNDRY_NAME"
[[ -n "${AZURE_AI_FOUNDRY_ENDPOINT:-}" ]]    && set_config AI_FOUNDRY_ENDPOINT "$AZURE_AI_FOUNDRY_ENDPOINT"
[[ -n "${AZURE_AI_FOUNDRY_PROJECT_NAME:-}" ]] && set_config AI_FOUNDRY_PROJECT_NAME "$AZURE_AI_FOUNDRY_PROJECT_NAME"
[[ -n "${AZURE_AI_PROJECT_ENDPOINT:-}" ]]    && set_config PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"

# AI Search
[[ -n "${AZURE_SEARCH_NAME:-}" ]] && set_config AI_SEARCH_NAME "$AZURE_SEARCH_NAME"

# Storage
set_config STORAGE_ACCOUNT_NAME "$STORAGE_ACCOUNT"

echo "  ✓ azure_config.env updated with deployment outputs"

echo ""
echo "✅ Post-provision complete!"
