"""Per-request frozen scope — resolved once by middleware, carried everywhere.

Module role:
    Replaces the pattern where every tool, router, and agent module independently
    calls ``load_scenario_yaml()`` + digs into nested dicts + falls back to env vars.
    The middleware now resolves everything once into a frozen ``RequestScope`` and
    stores it in a contextvar. Downstream code reads typed attributes.

Resolution happens once per request in ``build_request_scope()``:
    1. Scenario YAML parsed (via existing cached ``load_scenario_yaml()``)
    2. Service configs extracted into typed frozen dataclasses
    3. Search index names extracted into a flat dict
    4. Credential cached from ``get_azure_credential()``

Downstream usage (tools, agents, routers):
    from app.foundation.request_scope import get_request_scope
    scope = get_request_scope()
    workspace_id = scope.fabric_config.workspace_id   # typed, no dict diving

Key collaborators:
    - app/_middleware.py         — calls build_request_scope() once per request
    - app/scenario/_reader.py   — load_scenario_yaml() called by the builder
    - app/foundation/config.py  — Settings referenced on the scope

Dependents:
    Called by: tools/graph_explorer/*, tools/telemetry/*, tools/search/*,
    agents/_config.py, agents/_builder.py, routers/*
"""

from __future__ import annotations

import contextvars
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Typed service config dataclasses ─────────────────────────────────────────


@dataclass(frozen=True)
class FabricServiceConfig:
    """Pre-extracted Fabric service configuration from scenario.yaml.

    Eliminates the repeated pattern of:
        cfg.get("services", {}).get("fabric", {}).get("workspace_id")
    with a single attribute read.
    """

    workspace_id: str = ""
    graph_model_id: str = ""
    eventhouse_query_uri: str = ""
    kql_db_name: str = ""


@dataclass(frozen=True)
class CosmosGraphConfig:
    """Per-scenario Cosmos Gremlin (graph) binding from scenario.yaml.

    The endpoint + credentials stay account-global (env / settings); only the
    database + graph names are scenario-owned so packs can target separate
    Cosmos namespaces without an env change. Empty fields fall back to
    ``settings.*`` at the resolver seam (backward compatible).
    """

    database: str = ""
    graph: str = ""


@dataclass(frozen=True)
class CosmosTelemetryConfig:
    """Per-scenario Cosmos NoSQL (telemetry/alerts) binding from scenario.yaml."""

    database: str = ""
    telemetry_container: str = ""
    alerts_container: str = ""


# ── RequestScope ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RequestScope:
    """Frozen per-request snapshot — resolved once by middleware.

    Contains everything downstream code needs to execute a request:
    scenario identity, pre-extracted service configs, settings reference,
    and credential. No downstream code needs to call load_scenario_yaml()
    or os.getenv() for scenario-specific config.

    Attributes:
        scenario_name:       Active scenario for this request.
        graph_backend:       Active graph backend ID.
        llm_model:           Resolved LLM model (empty = per-agent in scenario.yaml).
        session_id:          Chat session ID (set by chat router, empty for non-chat).
        effective_backend:   Diagnostics metadata describing how the active
            graph backend was selected.
        scenario_yaml:       The full parsed scenario.yaml dict (cached reference).
        prompts_dir:         Absolute path to scenario's data/prompts/ directory.
        fabric_config:       Pre-extracted Fabric service config.
        cosmos_graph_config: Pre-extracted Cosmos Gremlin config.
        cosmos_telemetry_config: Pre-extracted Cosmos NoSQL telemetry config.
        search_indexes:      Dict of index_key → index_name from scenario.yaml.
        search_semantic_configs: Dict of index_key → semantic_config_name.
        settings:            Reference to the singleton Settings object.
    """

    # Identity
    scenario_name: str = ""
    llm_model: str = ""
    session_id: str = ""

    # Resolved scenario data
    scenario_yaml: dict = field(default_factory=dict)
    prompts_dir: Path = field(default_factory=lambda: Path("."))

    # Pre-extracted service configs
    fabric_config: FabricServiceConfig = field(default_factory=FabricServiceConfig)

    # Search indexes: key → index_name
    search_indexes: dict[str, str] = field(default_factory=dict)
    # Search semantic configs: key → semantic_config_name
    search_semantic_configs: dict[str, str] = field(default_factory=dict)

    # Per-scenario Cosmos bindings (db/graph/container names; endpoint stays env)
    cosmos_graph_config: CosmosGraphConfig = field(default_factory=CosmosGraphConfig)
    cosmos_telemetry_config: CosmosTelemetryConfig = field(default_factory=CosmosTelemetryConfig)

    # Infrastructure (singletons)
    settings: Any = None

    @property
    def graph_backend(self) -> str:
        """Always 'fabric' — kept as property for backward compat."""
        return "fabric"


# ── Contextvar ───────────────────────────────────────────────────────────────

_scope_var: contextvars.ContextVar[RequestScope] = contextvars.ContextVar(
    "request_scope"
)


def get_request_scope() -> RequestScope:
    """Return the current request's frozen scope.

    Safe to call from tools, agents, routers, services. Falls back to
    a default-constructed scope (empty configs) when called outside a
    request context (startup, background tasks, unit tests).

    Returns:
        The RequestScope for this request.
    """
    try:
        return _scope_var.get()
    except LookupError:
        # Outside request context — return a scope built from env vars
        return _build_fallback_scope()


def set_request_scope(scope: RequestScope) -> contextvars.Token:
    """Set the request scope for the current async task.

    Called by middleware at request start.

    Args:
        scope: The frozen RequestScope to set.

    Returns:
        Token for optional manual reset.
    """
    return _scope_var.set(scope)


def reset_request_scope(token: contextvars.Token) -> None:
    """Reset the scope contextvar to its previous value.

    Args:
        token: Token from set_request_scope().
    """
    _scope_var.reset(token)


# ── Builder ──────────────────────────────────────────────────────────────────


def build_request_scope(
    scenario_name: str,
    llm_model: str = "",
) -> RequestScope:
    """Build a frozen RequestScope from the resolved scenario name.

    Called once per request by middleware. Reads scenario.yaml (cached),
    extracts all service configs, and assembles the frozen snapshot.

    Args:
        scenario_name: Resolved scenario name (from env var).
        llm_model: Resolved LLM model (empty = per-agent default).

    Returns:
        A frozen RequestScope with all config pre-extracted.
    """
    from app.foundation.config import settings

    # Load scenario YAML (cached by scenario._reader)
    scenario_yaml: dict = {}
    prompts_dir = Path(".")
    if scenario_name:
        try:
            from app.scenario import load_scenario_yaml, get_scenario_dir
            scenario_yaml = load_scenario_yaml(scenario_name)
            sd = get_scenario_dir(scenario_name)
            if sd:
                prompts_dir = sd / "data" / "prompts"
        except Exception as e:
            logger.warning("request_scope.scenario_load_failed: %s", e)

    from app.scenario._deployment_registry import get_scenario_deployment
    deployment_record = get_scenario_deployment(scenario_name)

    # Extract Fabric service config from scenario.yaml
    fabric_config = _extract_fabric_config(scenario_yaml)

    # Extract per-scenario Cosmos bindings (db/graph/container) from scenario.yaml
    cosmos_graph_config, cosmos_telemetry_config = _extract_cosmos_config(scenario_yaml)

    # Extract search index names from deployment registry / scenario.yaml
    search_indexes, search_semantic_configs = _extract_search_indexes(scenario_yaml, deployment_record)

    return RequestScope(
        scenario_name=scenario_name,
        llm_model=llm_model,
        scenario_yaml=scenario_yaml,
        prompts_dir=prompts_dir,
        fabric_config=fabric_config,
        search_indexes=search_indexes,
        search_semantic_configs=search_semantic_configs,
        cosmos_graph_config=cosmos_graph_config,
        cosmos_telemetry_config=cosmos_telemetry_config,
        settings=settings,
    )


def _build_fallback_scope() -> RequestScope:
    """Build a scope for use outside request context (startup, background tasks).

    The operator-default scenario comes from ``settings.scenario_name`` (the
    single source of truth — pydantic binds SCENARIO_NAME at startup), not a
    direct os.environ read.
    """
    from app.foundation.config import settings
    return build_request_scope(
        scenario_name=settings.scenario_name or "",
        llm_model=os.environ.get("LLM_MODEL", ""),
    )


# ── Extractors ───────────────────────────────────────────────────────────────


def _extract_cosmos_config(cfg: dict) -> tuple[CosmosGraphConfig, CosmosTelemetryConfig]:
    """Extract per-scenario Cosmos bindings from ``data_sources``.

    Reads ``data_sources.graph`` / ``data_sources.telemetry`` when present.
    Missing fields stay empty and fall back to ``settings.*`` at the resolver
    seam (``tools/_cosmos.py``), so packs without the block keep the operator
    default namespace (backward compatible with telecom-playground-v2).
    """
    ds = cfg.get("data_sources", {}) if isinstance(cfg.get("data_sources"), dict) else {}
    graph = ds.get("graph", {}) if isinstance(ds.get("graph"), dict) else {}
    telem = ds.get("telemetry", {}) if isinstance(ds.get("telemetry"), dict) else {}
    graph_cfg = CosmosGraphConfig(
        database=str(graph.get("database", "") or ""),
        graph=str(graph.get("graph", "") or ""),
    )
    telem_cfg = CosmosTelemetryConfig(
        database=str(telem.get("database", "") or ""),
        telemetry_container=str(telem.get("telemetry_container", "") or ""),
        alerts_container=str(telem.get("alerts_container", "") or ""),
    )
    return graph_cfg, telem_cfg


def _extract_fabric_config(cfg: dict) -> FabricServiceConfig:
    """Extract FabricServiceConfig from scenario.yaml.

    Priority: services.fabric > backends.graph_config.fabric > env vars.
    """
    # Priority 1: services.fabric (canonical location)
    svc = cfg.get("services", {}).get("fabric", {})
    if svc.get("workspace_id") and svc.get("graph_model_id"):
        return FabricServiceConfig(
            workspace_id=svc["workspace_id"],
            graph_model_id=svc["graph_model_id"],
            eventhouse_query_uri=svc.get("eventhouse_query_uri", ""),
            kql_db_name=svc.get("kql_db_name", ""),
        )

    # Priority 2: backends.graph_config.fabric (backward compat)
    fabric_cfg = cfg.get("backends", {}).get("graph_config", {}).get("fabric", {})
    if fabric_cfg.get("workspace_id") and fabric_cfg.get("graph_model_id"):
        return FabricServiceConfig(
            workspace_id=fabric_cfg["workspace_id"],
            graph_model_id=fabric_cfg["graph_model_id"],
            eventhouse_query_uri=fabric_cfg.get("eventhouse_query_uri", ""),
            kql_db_name=fabric_cfg.get("kql_db_name", ""),
        )

    # Fallback: env vars
    return FabricServiceConfig(
        workspace_id=os.environ.get("FABRIC_WORKSPACE_ID", ""),
        graph_model_id=os.environ.get("FABRIC_GRAPH_MODEL_ID", ""),
        eventhouse_query_uri=os.environ.get("EVENTHOUSE_QUERY_URI", ""),
        kql_db_name=os.environ.get("FABRIC_KQL_DB_NAME", ""),
    )


def _extract_search_indexes(
    cfg: dict,
    deployment_record: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Extract search index names and semantic config names from registry or scenario.yaml.

    Returns:
        (index_names_dict, semantic_config_names_dict) — both keyed by index key.
    """
    indexes: dict[str, str] = {}
    semantic_configs: dict[str, str] = {}
    raw = cfg.get("data_sources", {}).get("search_indexes", {})
    for key, index_cfg in raw.items():
        if isinstance(index_cfg, dict):
            idx_name = index_cfg.get("index_name", "")
            if idx_name:
                indexes[key] = idx_name
            container = index_cfg.get("blob_container", "")
            if container:
                semantic_configs[key] = f"{container}-semantic"

    search_binding = deployment_record.get("bindings", {}).get("search", {})
    binding_indexes = search_binding.get("indexes", {})
    if isinstance(binding_indexes, dict):
        for key, index_name in binding_indexes.items():
            value = str(index_name).strip()
            if value:
                indexes[str(key)] = value

    binding_semantic_configs = search_binding.get("semantic_configs", {})
    if isinstance(binding_semantic_configs, dict):
        for key, semantic_name in binding_semantic_configs.items():
            value = str(semantic_name).strip()
            if value:
                semantic_configs[str(key)] = value

    return indexes, semantic_configs
