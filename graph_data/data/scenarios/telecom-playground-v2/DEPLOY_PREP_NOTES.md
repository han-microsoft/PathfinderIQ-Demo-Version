# Telecom Deploy Prep Notes

Date: 2026-03-08

Scope: This note records the validated prep and deployment requirements for `telecom-playground-v2` using the currently validated operator path documented in `graph_data/README.md`:

1. Upload scenario package with `scripts/package_uploader.py`.
2. Publish from inside the live app container with `scripts/publish_job.py`.
3. Target Cosmos Gremlin for graph data, Cosmos NoSQL for telemetry, and Azure AI Search for retrieval.

## Current state

- Present:
  - `scenario.yaml`
  - `package.yaml`
  - `graph_schema.yaml`
  - `search_manifest.yaml`
  - `deploy_manifest.yaml`
  - `topology.json`
  - scenario data under `data/`

## Validated deployment result

`telecom-playground-v2` was successfully uploaded and published on 2026-03-08 with package version `2026-03-08.3`.

Validated live state after publish:

- scenario registry entry: `is_ready: true`
- readiness status: `ready`
- active scenario: `telecom-playground-v2`
- graph target: `networkgraph` / `telecom-v2-topology`
- search indexes created and indexed successfully:
  - `telecom-v2-runbooks-index`
  - `telecom-v2-tickets-index`
  - `telecom-v2-equipment-index`
  - `telecom-v2-infra-specs-index`

## Original blocker that was cleared

The current package build and publish flow requires `package.yaml`.

Relevant code paths:

- `graph_data/scripts/packages/package_contract.py`
  - `load_package_contract_from_directory()` loads `scenario.yaml` and `package.yaml`
- `graph_data/scripts/packages/package_builder.py`
  - `build_package()` calls `load_package_contract()` before upload
- `graph_data/scripts/publish_job.py`
  - loads the uploaded package contract before invoking publishers

That file has now been added, which cleared the packaging and upload blocker.

## Required package.yaml contents

The new `package.yaml` should follow the same contract shape as the validated hello-world scenarios, but target the telecom resources:

```yaml
package:
  scenario: telecom-playground-v2
  version: dev
  created_at: "2026-03-08T00:00:00Z"
  source_commit: local

publish:
  mode: replace
  graph:
    enabled: true
    backend: cosmos-gremlin
    database: networkgraph
    graph: telecom-v2-topology
    schema_file: graph_schema.yaml
  telemetry:
    enabled: true
    backend: cosmos-nosql
    database: telemetry
    containers_from_scenario: true
  search:
    enabled: true
    backend: azure-ai-search
    manifest_file: search_manifest.yaml
    upload_files: true
```

Validation queries can still be added later. They were intentionally omitted from the first successful publish to reduce failure surface area.

## Infrastructure prep required by the current method

Before publish, the target Gremlin graph must already exist:

- database: `networkgraph`
- graph: `telecom-v2-topology`

The scenario manifest already lines up with the current Cosmos/Azure AI Search runtime targets:

- graph target: `telecom-v2-topology`
- telemetry database: `telemetry`
- search indexes:
  - `telecom-v2-runbooks-index`
  - `telecom-v2-tickets-index`
  - `telecom-v2-equipment-index`
  - `telecom-v2-infra-specs-index`

## Operational note from the successful publish

The first live publish attempt failed during Gremlin ingestion with Cosmos `429 RequestRateTooLarge` at the default graph throughput of `400 RU`.

The successful remediation was:

1. Increase graph throughput for `telecom-v2-topology` to `4000 RU`.
2. Re-run the same in-container `publish_job.py` command.

Result: graph ingestion completed, telemetry publication completed, and all four AI Search indexes finished indexing.

## Important config nuance

`scenario.yaml` currently mixes two different concepts:

- `data_sources.*` as scenario resource metadata for packaging and tooling
- active backend block:
  - `backends.graph: cosmosdb`
  - `backends.telemetry: cosmosdb`
  - `backends.search: azureaisearch`

The original Fabric-labeled connector values were misleading for the active Cosmos deployment path. They have now been normalized to Cosmos-compatible labels, but the broader structural split remains: runtime backend selection comes from `backends`, while `data_sources` still carries scenario resource metadata.

This split should still be cleaned up later so the same scenario file does not have to carry both runtime backend selection and publish/tooling metadata.

## Fabric manifest status

`deploy_manifest.yaml` is a separate Fabric deployment path. It references `scripts/fabric/deploy_scenario.py` and an Ontology workspace. It is not part of the currently validated Blob upload plus in-container publish workflow.

Conclusion: do not treat `deploy_manifest.yaml` as sufficient deploy prep for the current method.

## Recommended next revisit steps

1. Decide whether to keep `telecom-v2-topology` at `4000 RU` or scale it back after testing.
2. Clean up the connector metadata mismatch so `scenario.yaml` does not advertise Fabric connectors while the active runtime is Cosmos-based.
3. Add explicit post-publish validation queries once a stable canary query set is defined.
4. Verify end-to-end user flows in the UI against the live telecom scenario.