#!/usr/bin/env python3
"""Scenario pack contract validator.

Gates a use-case pack before it is seeded or deployed. Catches the failures that
otherwise only surface at runtime: missing prompt files, malformed tool specs,
absent data directories. Exit 0 = valid; exit 1 = contract violations found.

Contract (see build_spec/orchestrator_20260620_scenario_packs.md):
  required files:  scenario.yaml, graph_schema.yaml
  required dirs:   data/entities, data/telemetry, data/prompts
  agents:          every instruction file referenced must exist under the
                   prompts dir; every tool spec must be "module.path:function".
  search:          if search_manifest.yaml present, each declared knowledge
                   source dir must exist.

Usage:
    python3 graph_data/scripts/validate_scenario.py --scenario telecom-playground-v2
    python3 graph_data/scripts/validate_scenario.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
GRAPH_DATA_ROOT = SCRIPTS_DIR.parent
SCENARIOS_DIR = GRAPH_DATA_ROOT / "data" / "scenarios"

_REQUIRED_FILES = ("scenario.yaml", "graph_schema.yaml")
_REQUIRED_DIRS = ("data/entities", "data/telemetry", "data/prompts")


def _validate(scenario_dir: Path) -> list[str]:
    """Return a list of contract-violation messages (empty = valid)."""
    errors: list[str] = []
    name = scenario_dir.name

    for rel in _REQUIRED_FILES:
        if not (scenario_dir / rel).is_file():
            errors.append(f"[{name}] missing required file: {rel}")
    for rel in _REQUIRED_DIRS:
        if not (scenario_dir / rel).is_dir():
            errors.append(f"[{name}] missing required dir: {rel}")

    manifest_path = scenario_dir / "scenario.yaml"
    if not manifest_path.is_file():
        return errors  # cannot validate further without the manifest

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        errors.append(f"[{name}] scenario.yaml is not valid YAML: {exc}")
        return errors

    prompts_rel = (manifest.get("paths", {}) or {}).get("prompts", "data/prompts")
    prompts_dir = scenario_dir / prompts_rel

    agents = manifest.get("agents", {}) or {}
    for agent_id, cfg in agents.items():
        if agent_id == "default" or not isinstance(cfg, dict):
            continue
        for inst in cfg.get("instructions", []) or []:
            # {placeholder} tokens are runtime-resolved by agents/_prompts.py
            # (e.g. {graph_backend_prompt} -> query_language/gremlin.md), not
            # literal files in the pack — skip them.
            if "{" in inst and "}" in inst:
                continue
            if not (prompts_dir / inst).is_file():
                errors.append(f"[{name}] agent '{agent_id}' instruction file missing: {prompts_rel}/{inst}")
        for spec in cfg.get("tools", []) or []:
            if ":" not in spec or spec.count(":") != 1 or not all(spec.split(":")):
                errors.append(f"[{name}] agent '{agent_id}' malformed tool spec: '{spec}' (expected 'module.path:function')")

    search_manifest = scenario_dir / "search_manifest.yaml"
    indexes = (manifest.get("data_sources", {}) or {}).get("search_indexes", {}) or {}
    for idx_name, idx_cfg in indexes.items():
        src = (idx_cfg or {}).get("source")
        if src and not (scenario_dir / src).is_dir():
            errors.append(f"[{name}] search index '{idx_name}' source dir missing: {src}")
    if indexes and not search_manifest.is_file():
        errors.append(f"[{name}] data_sources.search_indexes declared but search_manifest.yaml is absent")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--scenario", help="Scenario folder name under data/scenarios/")
    grp.add_argument("--all", action="store_true", help="Validate every scenario pack")
    args = ap.parse_args()

    if args.all:
        targets = sorted(p for p in SCENARIOS_DIR.iterdir() if p.is_dir())
    else:
        target = SCENARIOS_DIR / args.scenario
        if not target.is_dir():
            print(f"ERROR: scenario not found: {target}", file=sys.stderr)
            return 2
        targets = [target]

    all_errors: list[str] = []
    for scenario_dir in targets:
        errs = _validate(scenario_dir)
        if errs:
            all_errors.extend(errs)
        else:
            print(f"OK  {scenario_dir.name}")

    if all_errors:
        print("\nCONTRACT VIOLATIONS:")
        for e in all_errors:
            print(f"  - {e}")
        print(f"\nVALIDATE_FAIL — {len(all_errors)} violation(s)")
        return 1

    print("\nVALIDATE_OK — all packs satisfy the contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
