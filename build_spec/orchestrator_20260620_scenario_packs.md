# Orchestrator spec — modular swappable scenario packs

Date: 2026-06-20. Owner: orchestrator. Status: design + phase-0 automation shipped.
Goal: a use-case = a self-contained **scenario pack** (agents + prompts + datasources +
provisioning) that swaps cleanly over a **constant backend core**. Request from operator:
(1) skills/scripts to automate creation+deploy of each data surface; (2) a config profile
that swaps entire use-cases (agents, tools, datasources).

## Decisions

| # | Decision | Rationale | Axis |
|---|---|---|---|
| DEC-1 | **Deploy-time swap first**; architect binding layer so runtime hot-swap is later additive work | Runtime hot-swap touches the protected live runtime (D1 RED zone). Deploy-time swap delivers modular packs + automation with low blast radius. | operability |
| DEC-2 | **Separate Cosmos database per scenario + `{scenario}-*` index prefix** | Clean isolation; multiple packs coexist; swap = flip active binding. telecom-v2 keeps db `pfiq` (backward compatible). | state |
| DEC-3 | **Machinery first**; telecom-v2 stays sole pack; add a **source-adapter seam** so real open data (RouteNet/SNDlib/GAIA — see OPEN_TELCO_DATASETS.md) normalizes into the standard CSV/doc shapes | Decouple "real data" from core; ingest adapters are leaf work. | experience |

## Current state (grounded)

| Layer | Modular today? | Evidence |
|---|---|---|
| Agents / prompts / tools | YES — declarative | `scenario.yaml` agents+tools+instructions; `agents/_builder.py`+`_tools.py` resolve by importlib |
| Search-index binding | partial | `scenario.yaml data_sources.search_indexes` declared per scenario |
| Graph / telemetry binding | NO — env-global | tools read `settings.cosmos_*` (`app/foundation/config.py` L86+); manifest has no graph/telemetry block; `services.fabric` is dead |
| Provisioning | NO orchestrator | manual fan-out: `seed_cosmos.py`, `azureaisearch/deploy_scenario.py`, `generate_topology.py` |
| Scenario contract | NONE | no schema/validator; bad packs fail at runtime not lint |

## Keystone gap (blocks clean swap)

Graph/telemetry datasource names are process-global env (`settings.cosmos_gremlin_database`,
`cosmos_gremlin_graph`, `cosmos_telemetry_container`, `cosmos_alerts_container`). Two scenarios
collide. **Fix (Phase 2, runtime — review-gated):** move per-scenario names into the manifest
`data_sources.graph` / `data_sources.telemetry` block; tools read the *active scenario's*
`ScenarioDataBindings`, not `settings.*`. `settings.*` keeps only account endpoints/creds.

## Phased plan

| Phase | Scope | Risk | Touches live runtime |
|---|---|---|---|
| P0 (DONE) | `provision_scenario.py` orchestrator + `validate_scenario.py` contract validator — additive scripts | none | no |
| P1 (DONE) | `data_sources.graph`/`telemetry` manifest block (declared, defaulted) — consumed by RequestScope | low | no (declaration only) |
| P2 (DONE) | `ScenarioDataBindings` context: `RequestScope.cosmos_graph_config`/`cosmos_telemetry_config`; `tools/_cosmos.py` resolvers read active scenario's binding, fallback `settings.*`; bounded per-scenario scope cache | medium | YES — shipped + live-probed |
| P3 (partial) | Runtime swap mechanism: `X-Scenario-Name` 3-tier resolve, `/api/scenarios[/select]`, `/api/preferences`, frontend `ScenarioSwitcher`, 2nd pack `demo-sandbox` | medium | YES — shipped + live-probed |
| P4 (deferred) | New-scenario scaffolder skill + source-adapter seam for real datasets (RouteNet/SNDlib + 3GPP KB) | low | no |
| P5 (deferred) | Full UI hot-swap without page reload (per-scenario client refetch instead of `window.location.reload`) | medium | yes |

## Scenario pack contract (target)

```
data/scenarios/<name>/
  scenario.yaml          # agents, tools, prompts, data_sources (graph+telemetry+search), ui
  graph_schema.yaml
  search_manifest.yaml
  provision.yaml         # P1: declares sources + target names (db, containers, index prefix)
  data/{entities,telemetry,knowledge,prompts}/
  ui/
```

`scenario.yaml data_sources` (P1 target shape):
```yaml
data_sources:
  graph:     { database: pfiq, graph: topology }        # default pfiq = backward-compat
  telemetry: { database: pfiq, telemetry_container: telemetry, alerts_container: alerts }
  search_indexes: { ... }                                # existing
```

## P0 artefacts (shipped this pass)

- `graph_data/scripts/provision_scenario.py` — one idempotent entry point; fans out to
  graph+telemetry seed, KB index, topology gen; per-surface flags + status; `--teardown` stub.
- `graph_data/scripts/validate_scenario.py` — contract gate: required files, prompt-file
  existence, tool-spec format. Exit nonzero on failure. Pre-deploy/CI hook.

## Pay-forward

| Learning | Destination | Reason |
|---|---|---|
| Graph/telemetry binding is env-global = swap blocker | this spec P2 + AUTODEV when P2 lands | keystone for multi-scenario |
| Provisioning was manual fan-out | `provision_scenario.py` | reproducible creation |
| Per-agent `model` baked at image build (L1) | AUTODEV L1 | runtime swap cannot depend on build-time values |
