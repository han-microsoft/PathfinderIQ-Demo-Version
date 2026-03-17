#!/usr/bin/env python3
"""Generate topology.json from graph_schema.yaml + entity CSVs.

Module role:
    Reads the declarative graph schema and CSV entity data, then produces
    a JSON file with the exact ``{topology_nodes, topology_edges}`` structure
    that both the frontend ``GraphTopologyViewer`` and the backend's in-memory
    ``MemoryGraph`` tool consume.

    The output is a self-contained topology snapshot — no runtime data fetching.
    The frontend loads it via ``/api/scenario/topology`` (served from the backend's
    ``load_topology()``), and the in-memory graph tool loads it via the same function.

Data flow:
    graph_schema.yaml + data/entities/*.csv → this script → topology.json

Node format in output:
    {"id": "CORE-SYD-01", "label": "CoreRouter", "properties": {...}}

Edge format in output:
    {"id": "connects_to:LINK-SYD-MEL→CORE-SYD-01", "source": "LINK-SYD-MEL",
     "target": "CORE-SYD-01", "label": "connects_to", "properties": {...}}

Key collaborators:
    - ``graph_schema.yaml``              — declarative vertex + edge definitions
    - ``data/scenarios/<name>/data/entities/*.csv`` — entity data files
    - Frontend ``GraphTopologyViewer``    — consumes the output JSON
    - Backend ``app.services.scenario.load_topology()`` — serves the output

Dependents:
    Called by: ``deploy.sh`` during data preparation step

Usage:
    python scripts/generate_topology_json.py [--scenario <name>] [--output path]

Default output: ../app/frontend/public/topology.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import yaml


def load_schema(schema_path: Path) -> dict:
    """Load and return the graph_schema.yaml as a parsed dict.

    Parameters:
        schema_path: Absolute path to the graph_schema.yaml file.

    Returns:
        Dict with ``vertices`` and ``edges`` lists, plus optional metadata.
    """
    with open(schema_path) as f:
        return yaml.safe_load(f)


def load_csv(csv_path: Path) -> list[dict]:
    """Load a CSV file and return rows as a list of dicts (keyed by header).

    Parameters:
        csv_path: Absolute path to the CSV file.

    Returns:
        List of row dicts with column headers as keys.
    """
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def build_nodes(
    schema: dict, data_dir: Path, graph_styles: dict | None = None,
) -> tuple[list[dict], dict[str, dict]]:
    """Build topology nodes from vertex definitions in graph_schema.yaml.

    For each vertex type, reads the corresponding CSV file and creates
    a node dict with ``id``, ``label``, and ``properties``. Also builds
    an index for fast node lookup during edge resolution.

    If ``graph_styles`` is provided (from scenario.yaml), injects ``_size``
    into each node's properties for frontend rendering.

    Parameters:
        schema: Parsed graph_schema.yaml dict with ``vertices`` list.
        data_dir: Path to the data/entities/ directory containing CSV files.
        graph_styles: Optional dict from scenario.yaml ``graph_styles.node_types``.

    Returns:
        Tuple of (nodes_list, nodes_by_id):
          - nodes_list: All node dicts in declaration order.
          - nodes_by_id: Index mapping node IDs (and ``label:id`` variants)
            to node dicts for O(1) lookup during edge building.
    """
    # Build a label → size lookup from graph_styles
    style_sizes: dict[str, int] = {}
    if graph_styles and "node_types" in graph_styles:
        for lbl, style in graph_styles["node_types"].items():
            if "size" in style:
                style_sizes[lbl] = style["size"]

    nodes: list[dict] = []
    nodes_by_id: dict[str, dict] = {}  # id → node

    for vertex in schema["vertices"]:
        label = vertex["label"]
        csv_file = vertex["csv_file"]
        id_column = vertex["id_column"]
        properties = vertex.get("properties", [])

        rows = load_csv(data_dir / csv_file)
        for row in rows:
            node_id = row[id_column]
            props = {col: row[col] for col in properties if col in row}
            # Inject visual size from graph_styles if available
            if label in style_sizes:
                props["_size"] = style_sizes[label]
            node = {
                "id": node_id,
                "label": label,
                "properties": props,
            }
            nodes.append(node)
            # Index by both bare ID and label:ID for flexible lookup
            nodes_by_id[node_id] = node
            nodes_by_id[f"{label}:{node_id}"] = node

    return nodes, nodes_by_id


def build_edges(
    schema: dict, data_dir: Path, nodes_by_id: dict[str, dict]
) -> list[dict]:
    """Build topology edges from edge definitions in the schema.

    For each edge definition, reads the junction CSV and creates directed
    edges between source and target nodes. Supports optional row filtering
    (e.g., only include rows where ``direction == 'source'``) and edge
    properties (static values or CSV column references).

    Parameters:
        schema: Parsed graph_schema.yaml dict with ``edges`` list.
        data_dir: Path to the data/entities/ directory containing CSV files.
        nodes_by_id: Node lookup index from ``build_nodes()``.

    Returns:
        List of edge dicts with ``id``, ``source``, ``target``, ``label``,
        and ``properties`` keys.

    Side effects:
        Prints warnings to stderr for edges referencing non-existent nodes.
    """
    edges: list[dict] = []
    edge_counter: dict[str, int] = {}  # for generating unique IDs

    for edge_def in schema["edges"]:
        label = edge_def["label"]
        csv_file = edge_def["csv_file"]
        source_def = edge_def["source"]
        target_def = edge_def["target"]
        edge_props_defs = edge_def.get("properties", [])
        filter_def = edge_def.get("filter")

        rows = load_csv(data_dir / csv_file)

        for row in rows:
            # Apply filter if defined
            if filter_def:
                filter_col = filter_def["column"]
                filter_val = filter_def["value"]
                if row.get(filter_col) != filter_val:
                    continue

            # Resolve source node
            source_label = source_def["label"]
            source_col = source_def["column"]
            source_id = row.get(source_col)
            if not source_id:
                continue

            # Resolve target node
            target_label = target_def["label"]
            target_col = target_def["column"]
            target_id = row.get(target_col)
            if not target_id:
                continue

            # Verify both nodes exist
            source_node = nodes_by_id.get(source_id) or nodes_by_id.get(
                f"{source_label}:{source_id}"
            )
            target_node = nodes_by_id.get(target_id) or nodes_by_id.get(
                f"{target_label}:{target_id}"
            )

            if not source_node or not target_node:
                print(
                    f"  WARN: Skipping edge {label} — "
                    f"source={source_id} (found={source_node is not None}), "
                    f"target={target_id} (found={target_node is not None})",
                    file=sys.stderr,
                )
                continue

            # Build edge properties
            props: dict = {}
            for prop_def in edge_props_defs:
                name = prop_def["name"]
                if "value" in prop_def:
                    props[name] = prop_def["value"]
                elif "column" in prop_def:
                    props[name] = row.get(prop_def["column"], "")

            # Generate a unique edge ID
            # Format: {label}:{source_id}→{target_id}
            edge_id = f"{label}:{source_node['id']}→{target_node['id']}"
            # Handle duplicate edge IDs (e.g., multiple hops on same path)
            if edge_id in edge_counter:
                edge_counter[edge_id] += 1
                edge_id = f"{edge_id}#{edge_counter[edge_id]}"
            else:
                edge_counter[edge_id] = 0

            edge = {
                "id": edge_id,
                "source": source_node["id"],
                "target": target_node["id"],
                "label": label,
                "properties": props,
            }
            edges.append(edge)

    return edges


def main() -> None:
    """Entry point — parse args, build topology, write JSON output.

    Steps:
        1. Resolve scenario directory and graph_schema.yaml path
        2. Parse schema and locate data directory
        3. Build nodes from vertex definitions + CSVs
        4. Build edges from edge definitions + CSVs (with node lookup index)
        5. Write assembled ``{topology_nodes, topology_edges}`` to output JSON

    Side effects:
        Creates output directory if needed. Writes topology.json file.
    """
    parser = argparse.ArgumentParser(
        description="Generate topology.json from graph schema + CSVs"
    )
    parser.add_argument(
        "--scenario",
        default=os.environ.get("DEFAULT_SCENARIO", ""),
        help="Scenario name (subfolder under data/scenarios/)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path (default: ../app/frontend/public/topology.json)",
    )
    args = parser.parse_args()

    if not args.scenario:
        parser.error("--scenario is required (or set DEFAULT_SCENARIO env var)")

    # Resolve paths relative to graph_data project root
    project_root = Path(__file__).resolve().parent.parent
    scenario_dir = project_root / "data" / "scenarios" / args.scenario
    schema_path = scenario_dir / "graph_schema.yaml"

    if not schema_path.exists():
        print(f"ERROR: Schema not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    # Default output: sibling app/frontend/public/topology.json
    output_path = Path(
        args.output
        or project_root.parent
        / "app"
        / "frontend"
        / "public"
        / "topology.json"
    )

    print(f"Schema:   {schema_path}")
    print(f"Output:   {output_path}")

    schema = load_schema(schema_path)
    data_dir = scenario_dir / schema.get("data_dir", "data/entities")

    print(f"Data dir: {data_dir}")
    print()

    # Load scenario.yaml for graph_styles (node sizes)
    scenario_yaml_path = scenario_dir / "scenario.yaml"
    graph_styles: dict | None = None
    if scenario_yaml_path.exists():
        with open(scenario_yaml_path) as f:
            scenario_cfg = yaml.safe_load(f)
        graph_styles = scenario_cfg.get("graph_styles")
        if graph_styles:
            print(f"Graph styles loaded: {len(graph_styles.get('node_types', {}))} node types")

    # Build nodes
    nodes, nodes_by_id = build_nodes(schema, data_dir, graph_styles)
    labels = sorted({n["label"] for n in nodes})
    label_counts = {l: sum(1 for n in nodes if n["label"] == l) for l in labels}
    print(f"Nodes: {len(nodes)} ({', '.join(f'{l}:{label_counts[l]}' for l in labels)})")

    # Build edges
    edges = build_edges(schema, data_dir, nodes_by_id)
    edge_labels = sorted({e["label"] for e in edges})
    edge_counts = {l: sum(1 for e in edges if e["label"] == l) for l in edge_labels}
    print(f"Edges: {len(edges)} ({', '.join(f'{l}:{edge_counts[l]}' for l in edge_labels)})")

    # Assemble output
    output = {
        "topology_nodes": nodes,
        "topology_edges": edges,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWritten {output_path} ({output_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
