/**
 * @module GraphCanvas
 *
 * Force-directed graph renderer — the interactive 2D canvas that
 * visualises the network topology.
 *
 * Wraps `react-force-graph-2d` with custom canvas rendering callbacks:
 *   - Nodes: filled circles with label text, coloured per node type
 *     via {@link useNodeColor}
 *   - Edges: lines with optional arrow heads and relationship labels
 *
 * Supports user interaction: hover tooltips (via callback props),
 * right-click context menu, click to select, drag to reposition nodes,
 * and scroll to zoom. Exposes a {@link GraphCanvasHandle} imperative
 * handle for parent-controlled actions (zoomToFit, setFrozen).
 *
 * @props
 *   - `nodes`, `edges`         — topology data arrays
 *   - `width`, `height`        — pixel dimensions for the canvas
 *   - `nodeDisplayField`       — per-label field name to show as node label
 *   - `nodeColorOverride`      — per-label colour hex overrides
 *   - `dataVersion`            — incremented on data change to trigger zoom-to-fit
 *   - `nodeLabelFontSize/Color`, `edgeLabelFontSize/Color` — label styling
 *   - `onNodeHover`, `onLinkHover`, `onNodeRightClick`, `onBackgroundClick`
 *   - `onMouseEnter`, `onMouseLeave` — for pause-on-hover simulation control
 *
 * @ref {@link GraphCanvasHandle}
 *   - `zoomToFit()` — smoothly zooms to fit all nodes
 *   - `setFrozen(boolean)` — freezes/unfreezes the physics simulation
 *
 * @collaborators
 *   - `react-force-graph-2d` (ForceGraph2D) — underlying renderer
 *   - {@link useNodeColor} — resolved node colours
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer}.
 */
import { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from './useTopology';
import { useNodeColor } from './useNodeColor';

type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

export interface GraphCanvasHandle {
  zoomToFit: () => void;
  setFrozen: (frozen: boolean) => void;
  centerOnNode: (x: number, y: number) => void;
}

interface GraphCanvasProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  width: number;
  height: number;
  nodeDisplayField: Record<string, string>;
  nodeColorOverride: Record<string, string>;
  dataVersion: number;
  nodeLabelFontSize?: number | null;
  nodeLabelColor?: string | null;
  edgeLabelFontSize?: number | null;
  edgeLabelColor?: string | null;
  nodeScale?: number;
  edgeWidth?: number;
  edgeColorOverride?: Record<string, string>;
  /** When true, dim all nodes/links except those flagged `properties._incident`. Default false = unchanged. */
  incidentFocus?: boolean;
  onNodeHover: (node: TopologyNode | null) => void;
  onLinkHover: (edge: TopologyEdge | null) => void;
  onNodeRightClick: (node: TopologyNode, event: MouseEvent) => void;
  onNodeSelect?: (node: TopologyNode) => void;
  onBackgroundClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(
  function GraphCanvas(
    { nodes, edges, width, height,
      nodeDisplayField, nodeColorOverride, dataVersion,
      nodeLabelFontSize, nodeLabelColor,
      edgeLabelFontSize, edgeLabelColor,
      nodeScale = 1,
      edgeWidth,
      edgeColorOverride,
      incidentFocus = false,
      onNodeHover, onLinkHover, onNodeRightClick, onBackgroundClick,
      onMouseEnter, onMouseLeave, onNodeSelect },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
    const [frozen, setFrozen] = useState(false);
    // One-shot auto-fit guard: frame once after the layout settles, then never
    // again — re-fitting on every engine cooldown (e.g. after a node drag) snaps
    // the viewport back and breaks pan/zoom navigation.
    const hasFitRef = useRef(false);

    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, 40),
      setFrozen: (f: boolean) => {
        setFrozen(f);
        if (!f) fgRef.current?.d3ReheatSimulation();
      },
      centerOnNode: (x: number, y: number) => {
        fgRef.current?.centerAt(x, y, 600);
        fgRef.current?.zoom(4, 600);
      },
    }), []);

    useEffect(() => {
      hasFitRef.current = false;
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => {
          if (hasFitRef.current) return;
          hasFitRef.current = true;
          fgRef.current?.zoomToFit(400, 40);
        }, 3500);
      }
    }, [dataVersion]);

    // Repaint once when Incident Focus toggles. resumeAnimation restarts the
    // render loop; on an already-settled graph the engine immediately re-cools,
    // so it renders ~one frame with no node movement and no viewport change. Do
    // NOT call pauseAnimation here — it hard-stops the render loop and leaves
    // pan/zoom visually frozen.
    useEffect(() => {
      const fg = fgRef.current as unknown as { resumeAnimation?: () => void } | undefined;
      fg?.resumeAnimation?.();
    }, [incidentFocus]);

    // Repaint once when the panel is resized. resume-only — see the Incident
    // Focus note above; pauseAnimation would freeze pan/zoom.
    useEffect(() => {
      const fg = fgRef.current as unknown as { resumeAnimation?: () => void } | undefined;
      fg?.resumeAnimation?.();
    }, [width, height]);

    // Spread nodes apart — the d3 default charge (-30) + link pull collapses
    // ~90 nodes into an unreadable blob. Apply strong repulsion + weak links,
    // re-applied over the first ~2s (forces can be re-created on data set).
    useEffect(() => {
      const fg = fgRef.current;
      if (!fg || nodes.length === 0) return;
      let n = 0;
      const apply = () => {
        const charge = fg.d3Force('charge') as { strength?: (s: number) => void } | undefined;
        const link = fg.d3Force('link') as
          { distance?: (d: number) => void; strength?: (s: number) => void } | undefined;
        charge?.strength?.(-550);
        link?.distance?.(120);
        link?.strength?.(0.2);
        fg.d3ReheatSimulation();
      };
      apply();
      const id = setInterval(() => { apply(); if (++n >= 8) clearInterval(id); }, 250);
      const fit = setTimeout(() => {
        if (hasFitRef.current) return;
        hasFitRef.current = true;
        fg.zoomToFit(600, 60);
      }, 2800);
      return () => { clearInterval(id); clearTimeout(fit); };
    }, [dataVersion, nodes.length]);

    const getNodeColor = useNodeColor(nodeColorOverride);

    const [themeColors, setThemeColors] = useState(() => {
      const s = getComputedStyle(document.documentElement);
      return {
        textPrimary: s.getPropertyValue('--color-text-primary').trim(),
        textMuted: s.getPropertyValue('--color-text-muted').trim(),
        borderDefault: s.getPropertyValue('--color-border-default').trim(),
        borderStrong: s.getPropertyValue('--color-border-strong').trim(),
      };
    });
    useEffect(() => {
      const observer = new MutationObserver(() => {
        const s = getComputedStyle(document.documentElement);
        setThemeColors({
          textPrimary: s.getPropertyValue('--color-text-primary').trim(),
          textMuted: s.getPropertyValue('--color-text-muted').trim(),
          borderDefault: s.getPropertyValue('--color-border-default').trim(),
          borderStrong: s.getPropertyValue('--color-border-strong').trim(),
        });
      });
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
      return () => observer.disconnect();
    }, []);

    const nodeCanvasObject = useCallback(
      (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const size = (Number(node.properties['_size']) || 6) * nodeScale;
        const color = getNodeColor(node.label);
        const isIncident = String(node.properties['_incident'] ?? '') === 'true';
        const isDiscounted = String(node.properties['_discounted'] ?? '') === 'true';
        const discounted = incidentFocus && isDiscounted;
        const dim = incidentFocus && !isIncident && !isDiscounted;

        ctx.save();
        if (dim) ctx.globalAlpha = 0.12;

        ctx.beginPath();
        ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
        // Discounted = examined then ruled out as unrelated → distinct violet.
        ctx.fillStyle = discounted ? '#A855F7' : color;
        ctx.fill();
        ctx.strokeStyle = 'rgba(226,232,240,0.30)';
        ctx.lineWidth = 0.6;
        ctx.stroke();

        // Incident-focus emphasis ring (amber halo on blast-radius nodes)
        if (incidentFocus && isIncident) {
          ctx.beginPath();
          ctx.arc(node.x!, node.y!, size + 2.5, 0, 2 * Math.PI);
          ctx.strokeStyle = '#FBBF24';
          ctx.lineWidth = 2.5 / globalScale;
          ctx.stroke();
        }

        // Discounted ring — violet dashed, "considered but ruled out".
        if (discounted) {
          ctx.beginPath();
          ctx.setLineDash([3 / globalScale, 3 / globalScale]);
          ctx.arc(node.x!, node.y!, size + 2.5, 0, 2 * Math.PI);
          ctx.strokeStyle = '#A855F7';
          ctx.lineWidth = 2 / globalScale;
          ctx.stroke();
          ctx.setLineDash([]);
        }

        const displayField = nodeDisplayField[node.label] ?? 'id';
        const label = displayField === 'id'
          ? node.id
          : String(node.properties[displayField] ?? node.id);

        const autoSize = Math.max(11 / globalScale, 4);
        const fontSize = nodeLabelFontSize != null ? nodeLabelFontSize / globalScale : autoSize;
        // Declutter: with ~90 nodes, always-on labels smear together. Show labels
        // only when zoomed in, or for incident nodes during Incident Focus.
        // (Hover always shows the name via the tooltip.)
        const showLabel = globalScale > 1.4 || (incidentFocus && isIncident) || discounted;
        if (fontSize > 0 && !dim && showLabel) {
          ctx.font = `600 ${fontSize}px 'Segoe UI', system-ui, sans-serif`;
          ctx.fillStyle = (incidentFocus && isIncident) ? '#FBBF24' : discounted ? '#A855F7' : (nodeLabelColor ?? '#E5E7EB');
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(label, node.x!, node.y! + size + 2);
        }
        ctx.restore();
      },
      [getNodeColor, nodeDisplayField, themeColors, nodeLabelFontSize, nodeLabelColor, nodeScale, incidentFocus],
    );

    const linkCanvasObjectMode = () => 'after' as const;
    const linkCanvasObject = useCallback(
      (link: GLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const src = link.source as GNode;
        const tgt = link.target as GNode;
        if (!src.x || !tgt.x) return;

        const midX = (src.x + tgt.x) / 2;
        const midY = (src.y! + tgt.y!) / 2;
        const autoSize = Math.max(8 / globalScale, 2.5);
        const fontSize = edgeLabelFontSize != null ? edgeLabelFontSize / globalScale : autoSize;

        // Only show edge (relationship) labels when zoomed in — otherwise ~111
        // labels smear across the graph.
        if (fontSize > 0 && globalScale > 1.7) {
          ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
          ctx.fillStyle = edgeLabelColor ?? 'rgba(148,163,184,0.85)';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(link.label, midX, midY);
        }
      },
      [themeColors, edgeLabelFontSize, edgeLabelColor],
    );

    const handleNodeDoubleClick = useCallback((node: GNode) => {
      onNodeSelect?.(node);
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(4, 600);
    }, [onNodeSelect]);

    const handleNodeHoverInternal = useCallback(
      (node: GNode | null) => onNodeHover(node as TopologyNode | null),
      [onNodeHover],
    );
    const handleLinkHoverInternal = useCallback(
      (link: GLink | null) => onLinkHover(link as TopologyEdge | null),
      [onLinkHover],
    );

    return (
      <div
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={{ width, height, touchAction: 'none' }}
      >
        <ForceGraph2D
          ref={fgRef}
          width={width}
          height={height}
          graphData={{ nodes: nodes as GNode[], links: edges as GLink[] }}
          backgroundColor="#0e1726"
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => 'replace'}
          nodeId="id"
          linkSource="source"
          linkTarget="target"
          linkColor={(link: GLink) => {
            if (incidentFocus) {
              const s = link.source as GNode; const t = link.target as GNode;
              const sInc = String(s?.properties?.['_incident'] ?? '') === 'true';
              const tInc = String(t?.properties?.['_incident'] ?? '') === 'true';
              if (sInc && tInc) return '#FBBF24';
              return 'rgba(148,163,184,0.05)';
            }
            if (edgeColorOverride && link.label && edgeColorOverride[link.label]) {
              return edgeColorOverride[link.label];
            }
            return 'rgba(148,163,184,0.28)';
          }}
          linkWidth={edgeWidth ?? 1.5}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={0.9}
          linkDirectionalArrowColor={() => themeColors.borderStrong}
          linkCanvasObjectMode={linkCanvasObjectMode}
          linkCanvasObject={linkCanvasObject}
          onNodeHover={handleNodeHoverInternal}
          onLinkHover={handleLinkHoverInternal}
          onNodeRightClick={onNodeRightClick as (node: GNode, event: MouseEvent) => void}
          onNodeClick={handleNodeDoubleClick}
          onBackgroundClick={onBackgroundClick}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.25}
          cooldownTicks={frozen ? 0 : Infinity}
          cooldownTime={5000}
          onEngineStop={() => {
            if (hasFitRef.current) return;
            hasFitRef.current = true;
            fgRef.current?.zoomToFit(500, 60);
          }}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
          /* Custom renderers depend on zoom (labels-on-zoom, incident emphasis);
             autoPauseRedraw=true skips redraws when idle, freezing pan/zoom. */
          autoPauseRedraw={false}
        />
      </div>
    );
  },
);
