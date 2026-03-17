import { describe, expect, it } from "vitest";

import { normalizeTopologyPayload } from "@/components/graph/useTopology";

describe("normalizeTopologyPayload", () => {
  it("fills missing node and edge properties with empty objects", () => {
    const normalized = normalizeTopologyPayload({
      topology_nodes: [
        { id: "node-1", label: "Service", properties: { Name: "Primary" } },
        { id: "node-2", label: "Service" },
      ],
      topology_edges: [
        { id: "edge-1", source: "node-1", target: "node-2", label: "depends_on" },
      ],
    });

    expect(normalized.nodes[0].properties).toEqual({ Name: "Primary" });
    expect(normalized.nodes[1].properties).toEqual({});
    expect(normalized.edges[0].properties).toEqual({});
    expect(normalized.meta).toEqual({
      node_count: 2,
      edge_count: 1,
      labels: ["Service"],
    });
  });
});