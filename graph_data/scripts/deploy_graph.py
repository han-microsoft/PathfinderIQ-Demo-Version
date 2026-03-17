#!/usr/bin/env python3
"""Deploy graph data to Fabric: CSV → Lakehouse → Ontology.

Usage:
    python3 scripts/deploy_graph.py --manifest data/scenarios/telecom-playground-v2/deploy_manifest.yaml
    python3 scripts/deploy_graph.py --workspace-id <ID> --scenario telecom-playground-v2 --lakehouse-name LH_TelecomV2 --ontology-name ONT_TelecomV2
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fabric"))

from deploy_scenario import build_parser, main as _deploy_main
from _stages import workspace, folder, lakehouse, ontology, verify

# Override the stage list to only run graph-related stages
import deploy_scenario
deploy_scenario.STAGES = [
    ("workspace", workspace),
    ("folder", folder),
    ("lakehouse", lakehouse),
    ("ontology", ontology),
    ("verify", verify),
]

if __name__ == "__main__":
    sys.exit(_deploy_main())
