/**
 * @module graph (types)
 *
 * TypeScript type definitions for graph topology data structures.
 *
 * Matches the `topology.json` format produced by `generate_topology_json.py`
 * and served by the FastAPI backend at `GET /api/scenario/topology`.
 *
 * - {@link TopologyNode} — a graph vertex (router, switch, server, etc.)
 *   with a label, arbitrary properties, and optional force-graph
 *   position fields (`x`, `y`, `fx`, `fy`).
 * - {@link TopologyEdge} — a graph edge (connection, dependency, etc.)
 *   with source/target references, a relationship label, and properties.
 * - {@link TopologyMeta} — computed summary (counts, distinct labels).
 *
 * @dependents
 *   Imported by useTopology, GraphCanvas, GraphTooltip, GraphContextMenu,
 *   and all graph sub-components.
 */

export interface TopologyNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}

export interface TopologyEdge {
  id: string;
  source: string | TopologyNode;
  target: string | TopologyNode;
  label: string;
  properties: Record<string, unknown>;
}

export interface TopologyMeta {
  node_count: number;
  edge_count: number;
  labels: string[];
}
