/**
 * @module GraphTopologyViewer
 *
 * Main graph container — orchestrates the full network topology
 * visualisation panel.
 *
 * Fetches topology data via {@link useTopology} and composes all graph
 * sub-components into a cohesive interactive viewer:
 *   - {@link GraphHeaderBar}   — title, node/edge counts, pause/refresh controls
 *   - {@link GraphToolbar}     — node type filter chips + color overrides
 *   - {@link GraphEdgeToolbar} — edge type filter chips + color overrides
 *   - {@link GraphCanvas}      — force-directed graph renderer (react-force-graph-2d)
 *   - {@link GraphTooltip}     — floating hover tooltip for nodes/edges
 *   - {@link GraphContextMenu} — right-click context menu for node actions
 *
 * Manages user customisation state (node display field, node/edge colour
 * overrides, label style, active label filters) and persists it to
 * `localStorage`.
 *
 * @props
 *   - `width`  — available pixel width (from parent ResizeObserver)
 *   - `height` — available pixel height (from parent ResizeObserver)
 *
 * @collaborators
 *   - {@link useTopology}            — fetches topology nodes/edges/meta
 *   - {@link usePausableSimulation}  — pause/resume physics engine
 *   - {@link useTooltipTracking}     — mouse-tracking for tooltip positioning
 *
 * @dependents
 *   Rendered by {@link MetricsBar} inside {@link ResizableGraph}.
 */
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { useTopology, TopologyNode, TopologyEdge } from './useTopology';
import { GraphCanvas, GraphCanvasHandle } from './GraphCanvas';
import { MapCanvas, MapCanvasHandle } from './MapCanvas';
import { GraphHeaderBar } from './GraphHeaderBar';
import { GraphToolbar } from './GraphToolbar';
import { GraphEdgeToolbar } from './GraphEdgeToolbar';
import { GraphTooltip } from './GraphTooltip';
import { GraphContextMenu } from './GraphContextMenu';
import { usePausableSimulation } from './usePausableSimulation';
import { useTooltipTracking } from './useTooltipTracking';
import { useNodeColor } from './useNodeColor';
import { COLOR_PALETTE, EDGE_COLOR_PALETTE } from './graphConstants';

interface GraphTopologyViewerProps {
  width: number;
  height: number;
}

export function GraphTopologyViewer({ width, height }: GraphTopologyViewerProps) {
  const { data, loading, error, refetch } = useTopology();
  const canvasRef = useRef<GraphCanvasHandle>(null);
  const mapCanvasRef = useRef<MapCanvasHandle>(null);

  const [viewMode, setViewMode] = useState<'graph' | 'map'>(() => {
    try {
      const stored = localStorage.getItem('graph-view-mode');
      return stored === 'graph' ? 'graph' : 'map';
    } catch { return 'map'; }
  });
  useEffect(() => {
    localStorage.setItem('graph-view-mode', viewMode);
  }, [viewMode]);

  const activeRef = viewMode === 'map' ? mapCanvasRef : canvasRef;

  const { isPaused, handleMouseEnter, handleMouseLeave, handleTogglePause, resetPause } =
    usePausableSimulation(activeRef as React.RefObject<GraphCanvasHandle>);

  const { tooltip, handleNodeHover, handleLinkHover } =
    useTooltipTracking<TopologyNode, TopologyEdge>();
  const [contextMenu, setContextMenu] = useState<{
    x: number; y: number; node: TopologyNode;
  } | null>(null);

  const handleNodeRightClick = useCallback((node: TopologyNode, event: MouseEvent) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY, node });
  }, []);

  const [dataVersion, setDataVersion] = useState(0);
  const prevNodeCountRef = useRef(data.nodes.length);
  useEffect(() => {
    if (data.nodes.length !== prevNodeCountRef.current) {
      prevNodeCountRef.current = data.nodes.length;
      setDataVersion((v) => v + 1);
    }
  }, [data.nodes.length]);

  // User customization (persisted to localStorage)
  const [nodeDisplayField, setNodeDisplayField] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem('graph-display-fields');
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });
  const [nodeColorOverride, setNodeColorOverride] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem('graph-colors');
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });

  const [activeLabels, setActiveLabels] = useState<string[]>([]);
  const [showNodeBar, setShowNodeBar] = useState(false);
  const [showEdgeBar, setShowEdgeBar] = useState(false);
  const [activeEdgeLabels, setActiveEdgeLabels] = useState<string[]>([]);
  const [edgeColorOverride, setEdgeColorOverride] = useState<Record<string, string>>(() => {
    try {
      const stored = localStorage.getItem('graph-edge-colors');
      return stored ? JSON.parse(stored) : {};
    } catch { return {}; }
  });

  const [labelStyle, setLabelStyle] = useState<{
    nodeFontSize: number | null;
    nodeColor: string | null;
    edgeFontSize: number | null;
    edgeColor: string | null;
    nodeScale: number;
    edgeWidth: number;
  }>(() => {
    try {
      const stored = localStorage.getItem('graph-label-style');
      const parsed = stored ? JSON.parse(stored) : {};
      return { nodeFontSize: null, nodeColor: null, edgeFontSize: null, edgeColor: null, nodeScale: 1, edgeWidth: 1.5, ...parsed };
    } catch { return { nodeFontSize: null, nodeColor: null, edgeFontSize: null, edgeColor: null, nodeScale: 1, edgeWidth: 1.5 }; }
  });

  // Persist customization
  useEffect(() => {
    localStorage.setItem('graph-display-fields', JSON.stringify(nodeDisplayField));
  }, [nodeDisplayField]);
  useEffect(() => {
    localStorage.setItem('graph-colors', JSON.stringify(nodeColorOverride));
  }, [nodeColorOverride]);
  useEffect(() => {
    localStorage.setItem('graph-edge-colors', JSON.stringify(edgeColorOverride));
  }, [edgeColorOverride]);
  useEffect(() => {
    localStorage.setItem('graph-label-style', JSON.stringify(labelStyle));
  }, [labelStyle]);

  const availableEdgeLabels = useMemo(
    () => [...new Set(data.edges.map((e) => e.label))].sort(),
    [data.edges],
  );

  // Filtering
  const filteredNodes = data.nodes.filter((n) => {
    if (activeLabels.length > 0 && !activeLabels.includes(n.label)) return false;
    return true;
  });
  const nodeIdSet = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = data.edges.filter((e) => {
    const srcId = typeof e.source === 'string' ? e.source : e.source.id;
    const tgtId = typeof e.target === 'string' ? e.target : e.target.id;
    if (!nodeIdSet.has(srcId) || !nodeIdSet.has(tgtId)) return false;
    if (activeEdgeLabels.length > 0 && !activeEdgeLabels.includes(e.label)) return false;
    return true;
  });

  const BAR_HEIGHT = 36;
  const TOOLBAR_HEIGHT = BAR_HEIGHT + (showNodeBar ? BAR_HEIGHT : 0) + (showEdgeBar ? BAR_HEIGHT : 0);

  return (
    <div className="h-full flex flex-col overflow-hidden border border-border bg-neutral-bg1">
      <GraphHeaderBar
        loading={loading}
        isPaused={isPaused}
        onTogglePause={handleTogglePause}
        onZoomToFit={() => canvasRef.current?.zoomToFit()}
        onRefresh={() => { refetch(); resetPause(); }}
        showNodeBar={showNodeBar}
        onToggleNodeBar={() => setShowNodeBar((v) => !v)}
        showEdgeBar={showEdgeBar}
        onToggleEdgeBar={() => setShowEdgeBar((v) => !v)}
        visibleNodeCount={filteredNodes.length}
        totalNodeCount={data.nodes.length}
        visibleEdgeCount={filteredEdges.length}
        totalEdgeCount={data.edges.length}
        nodeLabelFontSize={labelStyle.nodeFontSize}
        onNodeLabelFontSizeChange={(s) => setLabelStyle((prev) => ({ ...prev, nodeFontSize: s }))}
        nodeLabelColor={labelStyle.nodeColor}
        onNodeLabelColorChange={(c) => setLabelStyle((prev) => ({ ...prev, nodeColor: c }))}
        edgeLabelFontSize={labelStyle.edgeFontSize}
        onEdgeLabelFontSizeChange={(s) => setLabelStyle((prev) => ({ ...prev, edgeFontSize: s }))}
        edgeLabelColor={labelStyle.edgeColor}
        onEdgeLabelColorChange={(c) => setLabelStyle((prev) => ({ ...prev, edgeColor: c }))}
        nodeScale={labelStyle.nodeScale}
        onNodeScaleChange={(s) => setLabelStyle((prev) => ({ ...prev, nodeScale: s }))}
        edgeWidth={labelStyle.edgeWidth}
        onEdgeWidthChange={(w) => setLabelStyle((prev) => ({ ...prev, edgeWidth: w }))}
        nodeLabels={data.meta?.labels ?? []}
        edgeLabels={availableEdgeLabels}
        nodeColorOverride={nodeColorOverride}
        edgeColorOverride={edgeColorOverride}
        getNodeColor={useNodeColor(nodeColorOverride)}
        getEdgeColor={(label: string) => {
          if (edgeColorOverride[label]) return edgeColorOverride[label];
          const palette = EDGE_COLOR_PALETTE.length > 0 ? EDGE_COLOR_PALETTE : COLOR_PALETTE;
          let hash = 0;
          for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
          return palette[Math.abs(hash) % palette.length];
        }}
        onSetNodeColor={(label, color) =>
          setNodeColorOverride((prev) => ({ ...prev, [label]: color }))
        }
        onSetEdgeColor={(label, color) =>
          setEdgeColorOverride((prev) => ({ ...prev, [label]: color }))
        }
        onSearch={(query) => {
          /* Find the first node whose id contains the search query (case-insensitive) */
          const q = query.toLowerCase();
          const match = filteredNodes.find((n) =>
            n.id.toLowerCase().includes(q) ||
            n.label.toLowerCase().includes(q) ||
            Object.values(n.properties).some((v) => String(v).toLowerCase().includes(q))
          );
          if (match && match.x != null && match.y != null) {
            activeRef.current?.centerOnNode(match.x, match.y);
          }
        }}
        viewMode={viewMode}
        onToggleViewMode={() => setViewMode((v) => v === 'graph' ? 'map' : 'graph')}
        onFillCorners={() => mapCanvasRef.current?.fillCorners()}
      />

      {showNodeBar && (
        <GraphToolbar
          availableLabels={data.meta?.labels ?? []}
          activeLabels={activeLabels}
          onToggleLabel={(l) =>
            setActiveLabels((prev) =>
              prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
            )
          }
          nodeColorOverride={nodeColorOverride}
        />
      )}

      {showEdgeBar && (
        <GraphEdgeToolbar
          availableEdgeLabels={availableEdgeLabels}
          activeEdgeLabels={activeEdgeLabels}
          onToggleEdgeLabel={(l) =>
            setActiveEdgeLabels((prev) =>
              prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]
            )
          }
          edgeColorOverride={edgeColorOverride}
        />
      )}

      {error && (
        <div className="text-xs text-status-error px-3 py-1">{error}</div>
      )}

      {loading && data.nodes.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-text-muted animate-pulse">Loading topology…</span>
        </div>
      )}

      {!loading && !error && data.nodes.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-2">
            <p className="text-sm text-text-muted">No graph data available</p>
            <p className="text-xs text-text-muted/60">
              Generate topology.json from scenario CSVs to populate the graph.
            </p>
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 relative">
        {viewMode === 'map' ? (
          <MapCanvas
            ref={mapCanvasRef}
            nodes={filteredNodes}
            edges={filteredEdges}
            width={width}
            height={height - TOOLBAR_HEIGHT}
            nodeDisplayField={nodeDisplayField}
            nodeColorOverride={nodeColorOverride}
            edgeColorOverride={edgeColorOverride}
            dataVersion={dataVersion}
            nodeLabelFontSize={labelStyle.nodeFontSize}
            nodeLabelColor={labelStyle.nodeColor}
            edgeLabelFontSize={labelStyle.edgeFontSize}
            edgeLabelColor={labelStyle.edgeColor}
            nodeScale={labelStyle.nodeScale}
            edgeWidth={labelStyle.edgeWidth}
            onNodeHover={handleNodeHover}
            onLinkHover={handleLinkHover}
            onNodeRightClick={handleNodeRightClick}
            onBackgroundClick={() => setContextMenu(null)}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          />
        ) : (
          <GraphCanvas
            ref={canvasRef}
            nodes={filteredNodes}
            edges={filteredEdges}
            width={width}
            height={height - TOOLBAR_HEIGHT}
            nodeDisplayField={nodeDisplayField}
            nodeColorOverride={nodeColorOverride}
            edgeColorOverride={edgeColorOverride}
            dataVersion={dataVersion}
            nodeLabelFontSize={labelStyle.nodeFontSize}
            nodeLabelColor={labelStyle.nodeColor}
            edgeLabelFontSize={labelStyle.edgeFontSize}
            edgeLabelColor={labelStyle.edgeColor}
            nodeScale={labelStyle.nodeScale}
            edgeWidth={labelStyle.edgeWidth}
            onNodeHover={handleNodeHover}
            onLinkHover={handleLinkHover}
            onNodeRightClick={handleNodeRightClick}
            onBackgroundClick={() => setContextMenu(null)}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          />
        )}

        {isPaused && (
          <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded-full
                         bg-neutral-bg4 text-text-muted text-[10px]
                         transition-opacity duration-100">
            ⏸ Paused
          </div>
        )}
      </div>

      <GraphTooltip tooltip={tooltip} nodeColorOverride={nodeColorOverride} />
      <GraphContextMenu
        menu={contextMenu}
        onClose={() => setContextMenu(null)}
        onSetDisplayField={(label, field) =>
          setNodeDisplayField((prev) => ({ ...prev, [label]: field }))
        }
      />
    </div>
  );
}
