/**
 * @module useTopology
 *
 * Topology data hook — fetches the network graph (nodes + edges) from
 * `GET /api/scenario/topology`.
 *
 * The backend serves `topology.json` from the active scenario folder.
 * This hook normalises the response into `TopologyNode[]`,
 * `TopologyEdge[]`, and a computed `TopologyMeta` (counts, label list).
 *
 * Supports abort-on-refetch via `AbortController` to prevent stale
 * responses when the user triggers multiple rapid refreshes.
 *
 * @returns `{ data: { nodes, edges, meta }, loading, error, refetch }`
 *
 * @collaborators
 *   - Types imported from `@/types/graph` (TopologyNode, TopologyEdge, TopologyMeta)
 *
 * @dependents
 *   Used by {@link GraphTopologyViewer} to supply data to the entire
 *   graph panel component tree.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import type { TopologyNode, TopologyEdge, TopologyMeta } from '@/types/graph';

export type { TopologyNode, TopologyEdge, TopologyMeta };

interface TopologyData {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  meta: TopologyMeta | null;
}

type RawTopologyPayload = Record<string, unknown>;

/**
 * Normalize backend topology payloads so graph components can rely on a stable
 * shape even when older fixtures or generated files omit `properties`.
 */
export function normalizeTopologyPayload(json: RawTopologyPayload): TopologyData {
  const rawNodes = (json.topology_nodes as TopologyNode[] | undefined)
    ?? (json.nodes as TopologyNode[] | undefined)
    ?? [];
  const rawEdges = (json.topology_edges as TopologyEdge[] | undefined)
    ?? (json.edges as TopologyEdge[] | undefined)
    ?? [];

  const nodes = rawNodes.map((node) => ({
    ...node,
    properties: node && typeof node.properties === 'object' && node.properties !== null
      ? node.properties
      : {},
  }));
  const edges = rawEdges.map((edge) => ({
    ...edge,
    properties: edge && typeof edge.properties === 'object' && edge.properties !== null
      ? edge.properties
      : {},
  }));
  const labels = [...new Set(nodes.map((node) => node.label))].sort();

  return {
    nodes,
    edges,
    meta: {
      node_count: nodes.length,
      edge_count: edges.length,
      labels,
    },
  };
}

/**
 * Hook to load graph topology data from the backend /api/scenario/topology endpoint.
 * Fetches once on mount (single-scenario mode).
 */
export function useTopology() {
  const [data, setData] = useState<TopologyData>({ nodes: [], edges: [], meta: null });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchTopology = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);

    try {
      const { getTopology } = await import('@/api/scenarioApi');
      const json = await getTopology(ctrl.signal);
      setData(normalizeTopologyPayload(json));
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch once on mount (single-scenario mode)
  useEffect(() => {
    fetchTopology();
    return () => { abortRef.current?.abort(); };
  }, [fetchTopology]);

  return { data, loading, error, refetch: fetchTopology };
}
