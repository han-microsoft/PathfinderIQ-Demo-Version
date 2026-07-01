/**
 * OntologyCanvas — the growing knowledge graph in the Ontology Studio.
 *
 * A self-contained react-force-graph-2d canvas that accumulates nodes/edges
 * as documents are "extracted". Node colours reuse the main graph's palette so
 * the assembled ontology matches what operators see in the live graph view.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import { COLOR_PALETTE } from "@/components/graph/graphConstants";

export interface OntoNode {
  id: string;
  type: string;
}
export interface OntoLink {
  source: string;
  target: string;
  type: string;
}

interface OntologyCanvasProps {
  nodes: OntoNode[];
  links: OntoLink[];
  onNodeClick?: (id: string) => void;
}

/** Deterministic type -> colour, matching the main graph's autoColor(). */
export function typeColor(type: string): string {
  let hash = 0;
  for (const ch of type) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
  return COLOR_PALETTE[Math.abs(hash) % COLOR_PALETTE.length];
}

interface FGNode {
  id: string;
  type: string;
  x?: number;
  y?: number;
}

export function OntologyCanvas({ nodes, links, onNodeClick }: OntologyCanvasProps) {
  const fgRef = useRef<ForceGraphMethods<FGNode, OntoLink> | undefined>(undefined);
  const wrapRef = useRef<HTMLDivElement>(null);
  const nodeMapRef = useRef<Map<string, FGNode>>(new Map());
  const [dims, setDims] = useState({ w: 400, h: 400 });
  const [graphData, setGraphData] = useState<{ nodes: FGNode[]; links: OntoLink[] }>({
    nodes: [],
    links: [],
  });

  /* Measure the container so the force graph fills it. */
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setDims({ w: el.clientWidth, h: el.clientHeight });
    });
    ro.observe(el);
    setDims({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  /* Sync incoming nodes/links into stable node objects (preserve x/y so the
     existing layout is kept while new nodes settle in). */
  useEffect(() => {
    const map = nodeMapRef.current;
    const wantIds = new Set(nodes.map((n) => n.id));
    for (const n of nodes) {
      const existing = map.get(n.id);
      if (existing) existing.type = n.type;
      else map.set(n.id, { id: n.id, type: n.type });
    }
    for (const id of [...map.keys()]) if (!wantIds.has(id)) map.delete(id);

    const fgNodes = nodes.map((n) => map.get(n.id)!);
    const fgLinks = links
      .filter((l) => map.has(l.source) && map.has(l.target))
      .map((l) => ({ ...l }));
    setGraphData({ nodes: fgNodes, links: fgLinks });
    // Spread nodes so labels don't collide, then gently re-centre as it grows.
    const fg = fgRef.current;
    if (fg) {
      fg.d3Force("charge")?.strength(-260);
      const link = fg.d3Force("link") as { distance?: (d: number) => void } | undefined;
      link?.distance?.(90);
    }
    const t = setTimeout(() => fgRef.current?.zoomToFit(500, 60), 350);
    return () => clearTimeout(t);
  }, [nodes, links]);

  const paintNode = useMemo(
    () =>
      (node: FGNode, ctx: CanvasRenderingContext2D, scale: number) => {
        const x = node.x ?? 0;
        const y = node.y ?? 0;
        const r = 6;
        const color = typeColor(node.type);
        // Glow
        ctx.beginPath();
        ctx.arc(x, y, r + 3 / scale, 0, Math.PI * 2);
        ctx.fillStyle = color + "22";
        ctx.fill();
        // Node
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "#0b1220";
        ctx.lineWidth = 1.5 / scale;
        ctx.stroke();
        // Label
        const fontSize = Math.max(9, 11 / scale);
        ctx.font = `600 ${fontSize}px 'Segoe UI', system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "#cbd5e1";
        ctx.fillText(node.id, x, y + r + 2);
      },
    [],
  );

  return (
    <div ref={wrapRef} className="absolute inset-0">
      <ForceGraph2D
        ref={fgRef}
        width={dims.w}
        height={dims.h}
        graphData={graphData}
        backgroundColor="#0b1220"
        nodeRelSize={6}
        nodeCanvasObject={paintNode}
        nodeLabel={(n: FGNode) => `${n.id} · ${n.type}`}
        onNodeClick={(n: FGNode) => onNodeClick?.(n.id)}
        linkColor={() => "rgba(148,163,184,0.35)"}
        linkWidth={1.2}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={0.9}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={1.6}
        linkDirectionalParticleColor={() => "#38BDF8"}
        cooldownTicks={80}
        d3VelocityDecay={0.3}
      />
    </div>
  );
}
