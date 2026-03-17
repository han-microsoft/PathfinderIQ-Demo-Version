#!/usr/bin/env python3
"""Filter topology.json — remove vibration sensor nodes and their edges.

Reads the source telecom-playground topology.json, removes nodes whose
IDs match the vibration sensors, removes any edges referencing those
node IDs, writes the result to the scenario root.

Input:  telecom-playground/topology.json (92 nodes, 113 edges)
Output: topology.json (90 nodes, ~111 edges)
"""

import json
from pathlib import Path

# Resolve paths relative to this script's parent (the scenario root)
SCENARIO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SCENARIO = SCENARIO_ROOT.parent / "telecom-playground"
SOURCE_JSON = SOURCE_SCENARIO / "topology.json"
OUTPUT_JSON = SCENARIO_ROOT / "topology.json"

# Node IDs to remove — the two vibration sensors
EXCLUDED_NODE_IDS = {
    "SENS-AMP-GOULBURN-VIB-001",
    "SENS-AMP-ALBURY-VIB-001",
}


def main() -> None:
    """Read source topology, filter nodes and edges, write output."""
    with open(SOURCE_JSON, encoding="utf-8") as f:
        topo = json.load(f)

    # Filter nodes — remove vibration sensor nodes
    orig_node_count = len(topo["topology_nodes"])
    topo["topology_nodes"] = [
        n for n in topo["topology_nodes"]
        if n["id"] not in EXCLUDED_NODE_IDS
    ]
    removed_nodes = orig_node_count - len(topo["topology_nodes"])

    # Filter edges — remove any edge referencing excluded node IDs
    orig_edge_count = len(topo["topology_edges"])
    topo["topology_edges"] = [
        e for e in topo["topology_edges"]
        if e["source"] not in EXCLUDED_NODE_IDS
        and e["target"] not in EXCLUDED_NODE_IDS
    ]
    removed_edges = orig_edge_count - len(topo["topology_edges"])

    # Write output
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(topo, f, indent=2)

    print(f"topology.json: {len(topo['topology_nodes'])} nodes, {len(topo['topology_edges'])} edges")
    print(f"  Removed: {removed_nodes} nodes, {removed_edges} edges")
    print(f"  Output: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
