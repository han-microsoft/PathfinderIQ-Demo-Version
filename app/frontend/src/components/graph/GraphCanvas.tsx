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
  onNodeHover: (node: TopologyNode | null) => void;
  onLinkHover: (edge: TopologyEdge | null) => void;
  onNodeRightClick: (node: TopologyNode, event: MouseEvent) => void;
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
      onNodeHover, onLinkHover, onNodeRightClick, onBackgroundClick,
      onMouseEnter, onMouseLeave },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
    const [frozen, setFrozen] = useState(false);

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
      if (fgRef.current && nodes.length > 0) {
        setTimeout(() => fgRef.current?.zoomToFit(400, 40), 500);
      }
    }, [dataVersion]);

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
        const { textPrimary, borderDefault } = themeColors;

        ctx.beginPath();
        ctx.arc(node.x!, node.y!, size, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = borderDefault;
        ctx.lineWidth = 0.5;
        ctx.stroke();

        const displayField = nodeDisplayField[node.label] ?? 'id';
        const label = displayField === 'id'
          ? node.id
          : String(node.properties[displayField] ?? node.id);

        const autoSize = Math.max(10 / globalScale, 3);
        const fontSize = nodeLabelFontSize != null ? nodeLabelFontSize / globalScale : autoSize;
        if (fontSize > 0) {
          ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
          ctx.fillStyle = nodeLabelColor ?? textPrimary;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(label, node.x!, node.y! + size + 2);
        }
      },
      [getNodeColor, nodeDisplayField, themeColors, nodeLabelFontSize, nodeLabelColor, nodeScale],
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

        if (fontSize > 0) {
          ctx.font = `${fontSize}px 'Segoe UI', system-ui, sans-serif`;
          ctx.fillStyle = edgeLabelColor ?? themeColors.textMuted;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(link.label, midX, midY);
        }
      },
      [themeColors, edgeLabelFontSize, edgeLabelColor],
    );

    const handleNodeDoubleClick = useCallback((node: GNode) => {
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(4, 600);
    }, []);

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
          backgroundColor="transparent"
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => 'replace'}
          nodeId="id"
          linkSource="source"
          linkTarget="target"
          linkColor={(link: GLink) => {
            if (edgeColorOverride && link.label && edgeColorOverride[link.label]) {
              return edgeColorOverride[link.label];
            }
            return themeColors.borderDefault;
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
          d3VelocityDecay={0.3}
          cooldownTicks={frozen ? 0 : Infinity}
          cooldownTime={3000}
          enableNodeDrag={true}
          enableZoomInteraction={true}
          enablePanInteraction={true}
        />
      </div>
    );
  },
);
