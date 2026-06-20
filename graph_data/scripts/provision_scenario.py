#!/usr/bin/env python3
"""Scenario provisioning orchestrator — one entry point per use-case pack.

Fans out to the existing per-surface provisioners so creating/deploying a
scenario's data is a single idempotent command instead of a manual sequence:

    graph + telemetry  ->  seed_cosmos.py
    knowledge base     ->  azureaisearch/deploy_scenario.py
    frontend topology  ->  generate_topology.py

Per DEC-2 (build_spec/orchestrator_20260620_scenario_packs.md) each scenario
targets its own Cosmos database (default derived from the scenario's
``data_sources.graph.database`` / ``telemetry.database``; falls back to ``pfiq``
for backward compatibility with telecom-playground-v2).

Endpoints resolve in priority order: CLI flag > env var. This script makes no
Azure calls itself — it shells the proven sub-provisioners, each of which owns
its own SDK + auth.

Examples
--------
    # Full provision (graph + telemetry + KB + topology)
    python3 graph_data/scripts/provision_scenario.py --scenario telecom-playground-v2 \
        --gremlin-endpoint wss://...:443/ --nosql-endpoint https://...:443/ --upload-files

    # Just re-index the knowledge base
    python3 graph_data/scripts/provision_scenario.py --scenario telecom-playground-v2 \
        --kb --upload-files

    # Wipe + reseed graph/telemetry only
    python3 graph_data/scripts/provision_scenario.py --scenario telecom-playground-v2 \
        --graph --telemetry --wipe --gremlin-endpoint ... --nosql-endpoint ...
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
GRAPH_DATA_ROOT = SCRIPTS_DIR.parent
SCENARIOS_DIR = GRAPH_DATA_ROOT / "data" / "scenarios"


def _load_manifest(scenario_dir: Path) -> dict:
    manifest_path = scenario_dir / "scenario.yaml"
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _resolve_db_names(manifest: dict) -> tuple[str, str, str]:
    """Return (gremlin_database, gremlin_graph, nosql_database).

    Reads the P1 ``data_sources.graph`` / ``data_sources.telemetry`` block when
    present; otherwise falls back to the legacy ``pfiq`` / ``topology`` defaults
    so existing packs keep working unchanged.
    """
    ds = manifest.get("data_sources", {}) or {}
    graph = ds.get("graph", {}) or {}
    telem = ds.get("telemetry", {}) or {}
    gremlin_database = graph.get("database", "pfiq")
    gremlin_graph = graph.get("graph", "topology")
    nosql_database = telem.get("database", gremlin_database)
    return gremlin_database, gremlin_graph, nosql_database


def _run(label: str, cmd: list[str], env: dict) -> int:
    print(f"\n=== {label} ===\n$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, env=env)
    status = "OK" if proc.returncode == 0 else f"FAIL(rc={proc.returncode})"
    print(f"--- {label}: {status} ---", flush=True)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", required=True, help="Scenario folder name under data/scenarios/")
    # Surface selection (default: all). Any explicit flag narrows to the chosen surfaces.
    ap.add_argument("--graph", action="store_true", help="Seed graph (Cosmos Gremlin)")
    ap.add_argument("--telemetry", action="store_true", help="Seed telemetry (Cosmos NoSQL)")
    ap.add_argument("--kb", action="store_true", help="Provision + index the knowledge base (AI Search)")
    ap.add_argument("--topology", action="store_true", help="Regenerate frontend topology.json")
    # Endpoints (flag > env)
    ap.add_argument("--gremlin-endpoint", default=os.environ.get("COSMOS_GREMLIN_ENDPOINT", ""))
    ap.add_argument("--nosql-endpoint", default=os.environ.get("COSMOS_TELEMETRY_ENDPOINT", ""))
    # Passthrough options
    ap.add_argument("--upload-files", action="store_true", help="Upload KB docs to blob before indexing")
    ap.add_argument("--wipe", action="store_true", help="Wipe graph/telemetry containers before seeding")
    ap.add_argument("--teardown", action="store_true", help="(stub) Tear down scenario data — not yet implemented")
    args = ap.parse_args()

    scenario_dir = SCENARIOS_DIR / args.scenario
    if not scenario_dir.is_dir():
        print(f"ERROR: scenario not found: {scenario_dir}", file=sys.stderr)
        return 2

    if args.teardown:
        print("ERROR: --teardown not implemented yet (P0 stub). Remove Cosmos db + Search indexes manually.", file=sys.stderr)
        return 2

    # Default: run every surface unless the caller selected specific ones.
    selected_any = args.graph or args.telemetry or args.kb or args.topology
    do_graph = args.graph or not selected_any
    do_telemetry = args.telemetry or not selected_any
    do_kb = args.kb or not selected_any
    do_topology = args.topology or not selected_any

    manifest = _load_manifest(scenario_dir)
    gremlin_db, gremlin_graph, nosql_db = _resolve_db_names(manifest)

    # graph_data scripts expect PYTHONPATH=graph_data for package imports.
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{GRAPH_DATA_ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

    failures: list[str] = []

    if do_graph or do_telemetry:
        cmd = [
            sys.executable, str(SCRIPTS_DIR / "seed_cosmos.py"),
            "--scenario-dir", str(scenario_dir),
            "--gremlin-database", gremlin_db,
            "--gremlin-graph", gremlin_graph,
            "--nosql-database", nosql_db,
        ]
        if args.gremlin_endpoint:
            cmd += ["--gremlin-endpoint", args.gremlin_endpoint]
        if args.nosql_endpoint:
            cmd += ["--nosql-endpoint", args.nosql_endpoint]
        if args.wipe:
            cmd += ["--wipe"]
        if do_graph and not do_telemetry:
            cmd += ["--graph-only"]
        if do_telemetry and not do_graph:
            cmd += ["--telemetry-only"]
        label = "SEED graph+telemetry" if (do_graph and do_telemetry) else ("SEED graph" if do_graph else "SEED telemetry")
        if _run(label, cmd, env) != 0:
            failures.append(label)

    if do_kb:
        manifest_path = scenario_dir / "search_manifest.yaml"
        if not manifest_path.exists():
            print(f"WARN: no search_manifest.yaml in {scenario_dir}; skipping KB", file=sys.stderr)
        else:
            cmd = [
                sys.executable, str(SCRIPTS_DIR / "azureaisearch" / "deploy_scenario.py"),
                "--manifest", str(manifest_path),
            ]
            if args.upload_files:
                cmd += ["--upload-files"]
            if _run("KB index (AI Search)", cmd, env) != 0:
                failures.append("KB index")

    if do_topology:
        cmd = [
            sys.executable, str(SCRIPTS_DIR / "generate_topology.py"),
            "--scenario", args.scenario,
        ]
        if _run("topology.json", cmd, env) != 0:
            failures.append("topology")

    print("\n========================================")
    if failures:
        print(f"PROVISION_INCOMPLETE — failed surfaces: {', '.join(failures)}")
        return 1
    print("PROVISION_DONE — all selected surfaces succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
