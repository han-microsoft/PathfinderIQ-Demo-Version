"""Application settings via pydantic-settings.

Module role:
    Central configuration for the entire backend. Every runtime setting — LLM
    provider, Azure endpoints, Fabric credentials, search indexes, scenario
    name, token limits, CORS origins — is declared here and validated at import
    time by pydantic-settings.

Configuration source chain (first match wins):
    1. Environment variables (set by Container App config or shell env)
    2. ``control/.env`` dotenv file (resolved relative to this file: 4 parents up)

Design rationale:
    Tool modules (``tools/fabric/_constants.py``, ``tools/search/_search.py``)
    read env vars via ``os.getenv()`` directly. By using ``env_prefix=""`` with
    no namespace, pydantic-settings reads the *same* variable names. This avoids
    a translation layer and ensures one set of variable names everywhere.

Key collaborators:
    - ``control/.env`` — the runtime dotenv file (local dev)
    - ``main.py`` — imports the singleton ``settings`` at startup

Dependents:
    Imported by virtually every backend module. Treat as read-only after startup.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

# Resolve control/.env relative to this file:
# this file: app/backend/app/foundation/config.py → 4 parents up = repo root
_CONTROL_ENV = str(Path(__file__).resolve().parents[4] / "control" / ".env")


class Settings(BaseSettings):
    """Central configuration — one place, validated at startup.

    All fields have defaults suitable for local development (mock mode).
    Production values come from control/.env, which is populated by
    ``dev.sh`` merging outputs from ``graph_data/deploy.sh``.

    Groups:
        LLM — provider selection, API key, model, base URL
        Fabric — workspace/graph IDs, Eventhouse URI, KQL DB name
        Azure AI Search — endpoint, key, index names
        Scenario — active scenario name, graph_data override
        Context window — token limits for LLM calls
        Session store — in-memory vs external HTTP service
        Server — CORS origins, debug mode
    """

    model_config = SettingsConfigDict(
        env_prefix="",            # No prefix — reads LLM_PROVIDER, not APP_LLM_PROVIDER
        env_file=_CONTROL_ENV,    # Fallback dotenv path
        env_file_encoding="utf-8",
        extra="ignore",           # Silently ignore unrecognised env vars
    )

    # ── LLM provider ───────────────────────────────────────────────────────
    # Valid values: "openai" (direct API), "agent" (Azure AI Agent Framework),
    # "echo" (parrots input), "mock" (canned rich response). Factory in llm.py.
    llm_provider: str = "openai"
    llm_base_url: str = ""   # OpenAI-compatible endpoint; empty = official OpenAI API
    llm_api_key: str = ""    # Required for "openai" provider; unused by "agent"
    llm_model: str = ""  # Model deployment name — set per-agent in scenario.yaml or via LLM_MODEL env var

    # ── Microsoft Fabric ─────────────────────────────────────────────────
    # Read by tools/fabric/ via os.getenv() AND by this pydantic model.
    # FABRIC_WORKSPACE_ID + FABRIC_GRAPH_MODEL_ID enable query_graph (GQL).
    # EVENTHOUSE_QUERY_URI + FABRIC_KQL_DB_NAME enable query_telemetry (KQL).
    fabric_workspace_id: str = ""      # Fabric workspace GUID
    fabric_api_url: str = ""           # https://api.fabric.microsoft.com/v1
    fabric_graph_model_id: str = ""    # GUID of the ontology graph model
    fabric_scope: str = "https://api.fabric.microsoft.com/.default"
    eventhouse_query_uri: str = ""     # https://<cluster>.kusto.fabric.microsoft.com
    fabric_kql_db_name: str = ""       # KQL database name in the Eventhouse

    # ── Azure AI Search ──────────────────────────────────────────────────
    # Enables search_runbooks and search_tickets tools.
    # If AI_SEARCH_API_KEY is empty, DefaultAzureCredential is used.
    ai_search_endpoint: str = ""       # https://<name>.search.windows.net
    ai_search_api_key: str = ""        # Optional admin key
    runbooks_index_name: str = "runbooks-index"  # Synced from scenario.yaml by dev.sh
    tickets_index_name: str = "tickets-index"    # Synced from scenario.yaml by dev.sh

    # ── Scenario ─────────────────────────────────────────────────────────
    # Scenario folder name under graph_data/data/scenarios/.
    # Controls which prompts, tools, topology, and search indexes are active.
    scenario_name: str = ""
    graph_data_dir: str = ""  # Override path to graph_data root (auto-detected if empty)

    # ── Context window ───────────────────────────────────────────────────
    # Used by context_manager.py to trim conversation history before LLM calls.
    # Budget = max_context_tokens - max_response_tokens.
    max_context_tokens: int = 120_000   # Total input window budget (tokens)
    max_response_tokens: int = 4_096    # Reserved for completion output (tokens)
    system_prompt: str = "You are a helpful assistant."  # Default; overridden by scenario prompts

    # ── Session persistence ─────────────────────────────────────────────
    # Cosmos DB NoSQL endpoint. If set, CosmosSessionStore is used.
    # If empty or unreachable at startup, falls back to InMemorySessionStore.
    # RBAC-only auth — DefaultAzureCredential, no keys.
    cosmos_session_endpoint: str = ""
    cosmos_session_database: str = "sessions"
    cosmos_session_container: str = "conversations"
    cosmos_session_ttl: int = 604800  # 7 days

    # ── Authentication ───────────────────────────────────────────────────
    # When AUTH_ENABLED=false (local dev), all requests get an anonymous user.
    # When AUTH_ENABLED=true (production), JWT Bearer tokens are validated
    # against Entra ID JWKS endpoint. Multi-tenant: AUTH_TENANT_ID="common".
    auth_enabled: bool = True
    auth_client_id: str = ""  # REQUIRED when AUTH_ENABLED=true — set to your Entra app registration's Application (client) ID
    auth_tenant_id: str = "common"    # "common" for multi-tenant

    # ── Server ───────────────────────────────────────────────────────────
    # CORS origins: Vite dev server (5173) and alternative frontend port (3000).
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    debug: bool = False  # Enables DEBUG-level logging when true

    # ── Observability ────────────────────────────────────────────────────
    # Export target for OpenTelemetry: "" (noop), "console", "azure", "otlp".
    # Noop mode has zero overhead — instrumentation runs but discards all data.
    # Set OTEL_EXPORT_TARGET in control/.env or container config to enable.
    #
    # ── How to enable Azure Monitor / Application Insights ──────────────
    #
    # 1. Create an Application Insights resource in Azure Portal (or via
    #    Bicep/Terraform). Copy the Connection String from the Overview page.
    #
    # 2. Add two env vars to control/.env (local dev) or Container Apps
    #    configuration (production):
    #
    #      OTEL_EXPORT_TARGET=azure
    #      APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxx;IngestionEndpoint=https://...
    #
    # 3. Restart the backend. On startup you'll see:
    #      {"level": "INFO", "message": "Observability: export=azure", ...}
    #
    # That's it. Traces, metrics, and logs flow to App Insights automatically:
    #   - Every HTTP request gets a span (FastAPI auto-instrumentation)
    #   - Every outbound httpx call gets a child span (session store, Fabric, Search)
    #   - Every @traced_tool call gets a span with tool.name, duration, row_count
    #   - JSON structured logs are exported as App Insights "traces" table
    #   - Metric counters (tool.calls, tool.errors) appear in App Insights "customMetrics"
    #
    # View in Azure Portal:
    #   App Insights → Transaction Search    → distributed traces (end-to-end)
    #   App Insights → Logs (KQL)            → traces | where message == "tool.complete"
    #   App Insights → Metrics               → tool.calls, tool.duration_ms
    #   App Insights → Application Map       → service dependency graph
    #
    # To switch back to noop (zero export, zero overhead):
    #   OTEL_EXPORT_TARGET=
    #
    # To export to Grafana/Jaeger/Datadog via OTLP instead:
    #   OTEL_EXPORT_TARGET=otlp
    #   OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
    #
    otel_export_target: str = "console"  # Read by observability/_bootstrap.py
    applicationinsights_connection_string: str = ""  # Required when otel_export_target=azure
    otlp_endpoint: str = ""  # Required when otel_export_target=otlp

    # ── LLMOps Tracing ──────────────────────────────────────────────────
    # Separate from infra OTel. Captures per-invocation LLM data: token counts,
    # cost, model name, tool calls, duration. For operational dashboards and
    # audit trails.
    #
    # LLMOPS_BACKEND: "" (disabled), "jsonl" (local file), "cosmos" (future)
    llmops_backend: str = ""
    llmops_cosmos_ttl: int = 2592000  # 30 days — longer than session TTL (7 days)

    @model_validator(mode="after")
    def _validate_provider_config(self):
        """Validate required config for the selected LLM provider.

        Called automatically by pydantic at Settings instantiation time.
        For 'openai' provider, LLM_API_KEY or LLM_BASE_URL must be set.
        For 'agent' provider, AZURE_AI_PROJECT_ENDPOINT may arrive later
        via ConfigResolver — so we warn instead of failing at import time.
        """
        if self.llm_provider == "openai":
            if not self.llm_api_key and not self.llm_base_url:
                raise ValueError(
                    "LLM_PROVIDER=openai requires either LLM_API_KEY or "
                    "LLM_BASE_URL. Set in control/.env."
                )
        elif self.llm_provider == "agent":
            import os
            if not os.environ.get("AZURE_AI_PROJECT_ENDPOINT"):
                # Not fatal — ConfigResolver may set this during lifespan.
                # The agent provider will fail at first request if still missing.
                import logging
                logging.getLogger(__name__).info(
                    "AZURE_AI_PROJECT_ENDPOINT not set at import time — "
                    "ConfigResolver will populate at startup"
                )
        return self

    @model_validator(mode="after")
    def _validate_auth_config(self):
        """Fail fast if auth is enabled but client ID is missing.

        Without this, AUTH_ENABLED=true + AUTH_CLIENT_ID="" causes:
        - /api/auth_setup returns {clientId: ""} → MSAL.js crashes
        - _validate_token uses empty audience → all tokens rejected
        Both produce confusing errors at runtime. Better to crash at startup.
        """
        if self.auth_enabled and not self.auth_client_id:
            raise ValueError(
                "AUTH_ENABLED=true requires AUTH_CLIENT_ID. "
                "Set AUTH_CLIENT_ID to your Entra app registration's "
                "Application (client) ID."
            )
        return self


# Module-level singleton — instantiated at import time.
# Every other module imports this directly: ``from app.foundation.config import settings``
settings = Settings()
