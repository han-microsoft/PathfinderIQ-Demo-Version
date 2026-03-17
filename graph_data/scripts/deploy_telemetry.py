#!/usr/bin/env python3
"""Deploy telemetry data to Fabric Eventhouse: CSV → KQL tables.

Usage:
    python3 scripts/deploy_telemetry.py --manifest data/scenarios/telecom-playground-v2/deploy_manifest.yaml
    python3 scripts/deploy_telemetry.py --workspace-id <ID> --scenario telecom-playground-v2 --eventhouse-name EH_TelecomV2
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fabric"))

from deploy_scenario import build_parser, main as _deploy_main
from _stages import workspace, folder, eventhouse, verify

# Override the stage list to only run telemetry-related stages
import deploy_scenario
deploy_scenario.STAGES = [
    ("workspace", workspace),
    ("folder", folder),
    ("eventhouse", eventhouse),
    ("verify", verify),
]

if __name__ == "__main__":
    sys.exit(_deploy_main())
