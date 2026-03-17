#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# LLM Conversational UI — Dev Script
#
# Two modes:
#   ./dev.sh              Backend + frontend (default)
#   ./dev.sh install      Install all dependencies
#   ./dev.sh clean        Remove venvs, node_modules, build artifacts
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_BACKEND="$BACKEND/.venv"

GRAPH_DATA_DIR="$ROOT/../graph_data"
CONTROL_DIR="$ROOT/../control"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
DIM='\033[2m'
RESET='\033[0m'

# Portable in-place sed (macOS BSD sed requires -i '')
sedi() {
  if [[ "$OSTYPE" == darwin* ]]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

log()  { echo -e "${CYAN}▸${RESET} $*"; }
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
err()  { echo -e "${RED}✗${RESET} $*" >&2; }

# ── Load control plane ────────────────────────────────────────────────────────
#
# Sources control/.env (single source of truth for all runtime config).
# If graph_data/azure_config.env is newer, merges infra values first.
# Syncs prompts from the active scenario into control/prompts/.

load_control_plane() {
  # Ensure control/ dir exists
  mkdir -p "$CONTROL_DIR/prompts"

  # If control/.env doesn't exist, initialise from template
  if [[ ! -f "$CONTROL_DIR/.env" ]]; then
    if [[ -f "$CONTROL_DIR/.env.example" ]]; then
      cp "$CONTROL_DIR/.env.example" "$CONTROL_DIR/.env"
      log "Initialised control/.env from .env.example — fill in real values"
    elif [[ -f "$CONTROL_DIR/.env.template" ]]; then
      cp "$CONTROL_DIR/.env.template" "$CONTROL_DIR/.env"
      log "Initialised control/.env from template (deprecated — use .env.example)"
    else
      err "No control/.env or .env.example found"
      return 1
    fi
  fi

  # Merge infra values from graph_data/azure_config.env if it exists
  merge_infra_config

  # Source control/.env — all vars, no prefix, into environment
  set -a; source "$CONTROL_DIR/.env"; set +a
  ok "Loaded control/.env"

  # Sync index names from scenario.yaml
  sync_index_names

  # Verify scenario consistency between deploy and runtime
  verify_scenario_consistency

  # Summary of enabled tools
  echo ""
  local tools_enabled=()
  [[ -n "${FABRIC_GRAPH_MODEL_ID:-}" ]]  && tools_enabled+=("query_graph(GQL)")
  [[ -n "${COSMOS_GREMLIN_ENDPOINT:-}" ]] && tools_enabled+=("query_cosmos_graph(Gremlin)")
  [[ -n "${EVENTHOUSE_QUERY_URI:-}" ]]   && tools_enabled+=("query_telemetry(KQL)")
  [[ -n "${AI_SEARCH_ENDPOINT:-}${AZURE_AI_SEARCH_ENDPOINT:-}" ]] && tools_enabled+=("search_runbooks + search_tickets")
  if (( ${#tools_enabled[@]} > 0 )); then
    ok "Tools enabled:  ${tools_enabled[*]}"
  else
    log "No tools enabled (configure connection values in control/.env)"
  fi

  # Migration check: warn if old APP_* vars are in the environment
  if [[ -n "${APP_LLM_PROVIDER:-}" && -z "${LLM_PROVIDER:-}" ]]; then
    echo ""
    echo -e "${YELLOW}⚠  Old APP_ prefix detected (APP_LLM_PROVIDER=${APP_LLM_PROVIDER}).${RESET}"
    echo -e "${YELLOW}   Config has moved to control/.env with unprefixed var names.${RESET}"
    echo -e "${YELLOW}   Please update your environment or shell profile.${RESET}"
    echo ""
  fi
}

merge_infra_config() {
  local src="$GRAPH_DATA_DIR/azure_config.env"
  [[ -f "$src" ]] || return 0

  # Only merge if azure_config.env is newer than control/.env
  if [[ "$src" -nt "$CONTROL_DIR/.env" ]]; then
    log "Merging updated infra values from graph_data/azure_config.env"

    # Source infra config to get values
    local _tmp_env
    _tmp_env=$(mktemp)
    source "$src"

    # Map infra vars → control/.env var names (only update if set in source)
    local -A mappings=(
      [AZURE_AI_PROJECT_ENDPOINT]="${PROJECT_ENDPOINT:-}"
      [AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME]="${CHAT_MODEL_DEPLOYMENT:-}"
      [FABRIC_WORKSPACE_ID]="${FABRIC_WORKSPACE_ID:-}"
      [FABRIC_GRAPH_MODEL_ID]="${FABRIC_GRAPH_MODEL_ID:-}"
      [EVENTHOUSE_QUERY_URI]="${EVENTHOUSE_QUERY_URI:-}"
      [FABRIC_KQL_DB_NAME]="${FABRIC_KQL_DB_NAME:-}"
      [FABRIC_API_URL]="${FABRIC_API_URL:-}"
      [FABRIC_SCOPE]="${FABRIC_SCOPE:-}"
      [SCENARIO_NAME]="${DEFAULT_SCENARIO:-}"
      [RUNBOOKS_INDEX_NAME]="${RUNBOOKS_INDEX_NAME:-}"
      [TICKETS_INDEX_NAME]="${TICKETS_INDEX_NAME:-}"
      [COSMOS_GREMLIN_ENDPOINT]="${COSMOS_GREMLIN_ENDPOINT:-}"
      [COSMOS_GREMLIN_DATABASE]="${COSMOS_GREMLIN_DATABASE:-}"
      [COSMOS_GREMLIN_GRAPH]="${COSMOS_GREMLIN_GRAPH:-}"
    )

    # Derive AI_SEARCH_ENDPOINT from AI_SEARCH_NAME
    if [[ -n "${AI_SEARCH_NAME:-}" ]]; then
      mappings[AI_SEARCH_ENDPOINT]="https://${AI_SEARCH_NAME}.search.windows.net"
    fi

    # Update control/.env: replace existing values, don't duplicate
    for key in "${!mappings[@]}"; do
      local val="${mappings[$key]}"
      [[ -z "$val" ]] && continue
      if grep -q "^${key}=" "$CONTROL_DIR/.env" 2>/dev/null; then
        sedi "s|^${key}=.*|${key}=${val}|" "$CONTROL_DIR/.env"
      else
        echo "${key}=${val}" >> "$CONTROL_DIR/.env"
      fi
    done

    rm -f "$_tmp_env"
    ok "Infra values merged into control/.env"
  fi
}

sync_index_names() {
  # Sync search index names from scenario.yaml into control/.env
  # (prompts are read directly from the scenario folder by the loader)
  local scenario="${SCENARIO_NAME:-${DEFAULT_SCENARIO:-}}"
  [[ -n "$scenario" ]] || return 0

  local scenario_yaml="$GRAPH_DATA_DIR/data/scenarios/$scenario/scenario.yaml"
  if [[ -f "$scenario_yaml" ]] && command -v python3 &>/dev/null; then
    local idx_update
    idx_update=$(python3 -c "
import yaml, sys
with open('$scenario_yaml') as f:
    cfg = yaml.safe_load(f) or {}
ds = cfg.get('data_sources', {}).get('search_indexes', {})
rb = ds.get('runbooks', {}).get('index_name', '')
tk = ds.get('tickets', {}).get('index_name', '')
if rb: print(f'RUNBOOKS_INDEX_NAME={rb}')
if tk: print(f'TICKETS_INDEX_NAME={tk}')
" 2>/dev/null) || true
    if [[ -n "$idx_update" ]]; then
      while IFS= read -r line; do
        local key="${line%%=*}"
        local val="${line#*=}"
        sedi "s|^${key}=.*|${key}=${val}|" "$CONTROL_DIR/.env"
        export "$key=$val"
      done <<< "$idx_update"
      ok "Index names synced from scenario.yaml"
    fi
  fi
}

verify_scenario_consistency() {
  # Read deployed scenario from azure_config.env (if it exists)
  local infra_config="$GRAPH_DATA_DIR/azure_config.env"
  [[ -f "$infra_config" ]] || return 0

  local deployed
  deployed=$(grep '^DEFAULT_SCENARIO=' "$infra_config" 2>/dev/null | cut -d= -f2 || true)
  local active="${SCENARIO_NAME:-${DEFAULT_SCENARIO:-}}"

  if [[ -n "$deployed" && -n "$active" && "$deployed" != "$active" ]]; then
    echo ""
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "  ${RED}⚠  SCENARIO MISMATCH${RESET}"
    echo -e "  ${YELLOW}Deployed data:${RESET}  $deployed  ${DIM}(graph_data/azure_config.env)${RESET}"
    echo -e "  ${YELLOW}Active config:${RESET}  $active  ${DIM}(control/.env)${RESET}"
    echo -e "  ${DIM}Prompts and search indexes may be inconsistent with deployed data.${RESET}"
    echo -e "  ${DIM}Fix: graph_data/deploy.sh --scenario $active${RESET}"
    echo -e "  ${DIM}  or: edit control/.env → SCENARIO_NAME=$deployed${RESET}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
  fi
}

require_cmd() {
  command -v "$1" &>/dev/null || { err "'$1' not found"; exit 1; }
}

# ── Install ──────────────────────────────────────────────────────────────────

install_venv() {
  local dir="$1" venv="$2"
  require_cmd uv
  [[ -d "$venv" ]] || uv venv "$venv"
  uv pip install --quiet --prerelease allow -e "$dir" -p "$venv/bin/python"
}

install_backend() {
  log "Installing backend deps"
  install_venv "$BACKEND" "$VENV_BACKEND"
  ok "Backend ready"
}

install_frontend() {
  log "Installing frontend deps"
  require_cmd node && require_cmd npm
  cd "$FRONTEND" && npm install --silent
  ok "Frontend ready"
}

install_all() {
  install_backend
  install_frontend
}

# ── Kill stale ───────────────────────────────────────────────────────────────

kill_stale() {
  local killed=false
  for p in "uvicorn app.main" "vite.*--port 5173"; do
    pkill -f "$p" 2>/dev/null && killed=true
  done
  $killed && sleep 1 && log "Killed stale processes"
  return 0
}

# ── Run services ─────────────────────────────────────────────────────────────

PIDS=()

run_backend() {
  local port="${1:-9000}"
  log "Starting gateway on :$port"
  [[ -x "$VENV_BACKEND/bin/uvicorn" ]] || install_backend
  # Only default to mock if no env var set
  if [[ -z "${LLM_PROVIDER:-}" ]]; then
    export LLM_PROVIDER="mock"
  fi
  cd "$BACKEND"
  "$VENV_BACKEND/bin/python3" -m uvicorn app.main:app \
    --reload --host 0.0.0.0 --port "$port" --log-level info &
  PIDS+=($!)
}

run_frontend() {
  log "Starting frontend on :5173"
  [[ -d "$FRONTEND/node_modules" ]] || install_frontend
  # Clear Vite's pre-bundle cache to prevent stale module serving.
  # Without this, HMR can serve old pre-bundled deps after code changes.
  rm -rf "$FRONTEND/node_modules/.vite" 2>/dev/null
  cd "$FRONTEND"
  npx vite --host 0.0.0.0 --port 5173 &
  PIDS+=($!)
}

cleanup() {
  echo ""
  log "Shutting down…"
  for pid in "${PIDS[@]+"${PIDS[@]}"}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  ok "Stopped"
}

# ── Monolith mode ────────────────────────────────────────────────────────────

run_monolith() {
  kill_stale
  trap cleanup EXIT INT TERM

  load_control_plane
  run_backend
  run_frontend

  echo ""
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "  ${CYAN}Mode${RESET}      ${DIM}Monolith (sessions in-memory inside gateway)${RESET}"
  echo -e "  ${CYAN}Gateway${RESET}   http://localhost:9000"
  echo -e "  ${CYAN}Frontend${RESET}  http://localhost:5173"
  echo -e "  ${CYAN}LLM${RESET}       ${LLM_PROVIDER:-mock}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
  echo -e "  ${DIM}Press Ctrl+C to stop${RESET}"
  echo ""
  wait
}

# ── Clean ────────────────────────────────────────────────────────────────────

clean() {
  log "Cleaning build artifacts"
  rm -rf "$VENV_BACKEND"
  rm -rf "$FRONTEND/node_modules" "$FRONTEND/dist"
  rm -rf "$BACKEND"/__pycache__ "$BACKEND"/app/__pycache__ "$BACKEND"/app/services/__pycache__
  ok "Clean complete"
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  case "${1:-all}" in
    all|monolith) run_monolith ;;
    install)      install_all  ;;
    clean)        clean        ;;
    *)
      echo "Usage: $0 {all|install|clean}"
      echo ""
      echo "  all            Backend + frontend (sessions via Cosmos or in-memory)"
      echo "  install        Install all dependencies"
      echo "  clean          Remove venvs, node_modules, dist"
      exit 1
      ;;
  esac
}

main "$@"
