/**
 * @module MapCanvas
 *
 * Paper road-map renderer — an alternative to {@link GraphCanvas} that
 * re-skins the force-directed graph as a hand-drawn road atlas.
 *
 * Uses the same `react-force-graph-2d` engine underneath but replaces
 * every visual callback with map-style rendering:
 *   - Background: cream paper with city-block grid, parks, water
 *   - Edges: roads with casing, curvature, road-code labels
 *   - Nodes: town pins with callout-box labels
 *   - Overlay: compass rose, "PathfinderIQ" banner, legend
 *
 * The component exposes an identical {@link GraphCanvasHandle} imperative
 * handle so it can be swapped in place of GraphCanvas without changes to
 * the parent.
 *
 * @props  Same as {@link GraphCanvas}.
 * @ref    {@link GraphCanvasHandle}
 *
 * @collaborators
 *   - `react-force-graph-2d` — underlying engine
 *   - {@link mapRendering} — pure canvas drawing helpers
 *   - {@link useNodeColor} — node colour resolution
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer} when map view is active.
 */
import { useState, useRef, useCallback, useEffect, useMemo, forwardRef, useImperativeHandle, type CSSProperties } from 'react';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import type { TopologyNode, TopologyEdge } from './useTopology';
import { useNodeColor } from './useNodeColor';
import {
  computeMapFeatures,
  drawPaperBackground,
  drawRoad,
  drawRoadLabel,
  drawTownMarker,
  drawCompassRose,
  drawMapLegend,
  drawPaperEdge,
  getViewportBounds,
  classifyRoad,
  roadCode,
  ROAD_STYLES,
  type MapFeatures,
} from './mapRendering';

type GNode = NodeObject<TopologyNode>;
type GLink = LinkObject<TopologyNode, TopologyEdge>;

/* Re-export the same handle type as GraphCanvas */
export interface MapCanvasHandle {
  zoomToFit: () => void;
  fillCorners: () => void;
  setFrozen: (frozen: boolean) => void;
  centerOnNode: (x: number, y: number) => void;
  setFlat: (flat: boolean) => void;
}

interface MapCanvasProps {
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
  incidentFocus?: boolean;
  onNodeHover: (node: TopologyNode | null) => void;
  onLinkHover: (edge: TopologyEdge | null) => void;
  onNodeRightClick: (node: TopologyNode, event: MouseEvent) => void;
  onNodeSelect?: (node: TopologyNode) => void;
  onBackgroundClick: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export const MapCanvas = forwardRef<MapCanvasHandle, MapCanvasProps>(
  function MapCanvas(
    {
      nodes, edges, width, height,
      nodeDisplayField, nodeColorOverride, dataVersion,
      nodeScale = 1,
      incidentFocus = false,
      onNodeHover, onLinkHover, onNodeRightClick, onBackgroundClick,
      onMouseEnter, onMouseLeave, onNodeSelect,
    },
    ref,
  ) {
    const fgRef = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
    const [frozen, setFrozen] = useState(false);
    // Flat “fill corners” is the default — a clean, operations-console layout
    // (no 3D paper tilt). Users can still toggle the tilted-paper view.
    const [flat, setFlat] = useState(true);
    // One-shot auto-fit guard: frame the layout once after it settles, then
    // never again — re-fitting on every engine cooldown (e.g. after a node
    // drag) snaps the viewport back and breaks pan/zoom navigation.
    const hasFitRef = useRef(false);

    useImperativeHandle(ref, () => ({
      zoomToFit: () => fgRef.current?.zoomToFit(400, flat ? 14 : 60),
      fillCorners: () => {
        setFlat((prev) => {
          const next = !prev;
          /* After the layout recalculates with new dimensions, zoom to fill. */
          setTimeout(() => fgRef.current?.zoomToFit(400, next ? 10 : 60), 100);
          return next;
        });
      },
      setFrozen: (f: boolean) => {
        setFrozen(f);
        if (!f) fgRef.current?.d3ReheatSimulation();
      },
      centerOnNode: (x: number, y: number) => {
        fgRef.current?.centerAt(x, y, 600);
        fgRef.current?.zoom(4, 600);
      },
      setFlat: (f: boolean) => {
        setFlat(f);
        setTimeout(() => fgRef.current?.zoomToFit(400, f ? 10 : 60), 100);
      },
    }), []);

    useEffect(() => {
      hasFitRef.current = false;
      if (fgRef.current && nodes.length > 0) {
        // Fallback fit only — onEngineStop normally fits first once the spacing
        // forces settle (~2-4s). Long timeout avoids framing a half-spread blob.
        setTimeout(() => {
          if (hasFitRef.current) return;
          hasFitRef.current = true;
          fgRef.current?.zoomToFit(400, flat ? 14 : 60);
        }, 3500);
      }
    }, [dataVersion]);

    // Repaint once when Incident Focus toggles. resumeAnimation restarts the
    // render loop; on an already-settled graph the engine immediately re-cools
    // (onEngineStop), so it renders ~one frame with no node movement and no
    // viewport change. Do NOT call pauseAnimation here — it hard-stops the
    // render loop, which then leaves pan/zoom visually frozen (the transform
    // updates but nothing repaints).
    useEffect(() => {
      const fg = fgRef.current as unknown as { resumeAnimation?: () => void } | undefined;
      fg?.resumeAnimation?.();
    }, [incidentFocus]);

    // Repaint once when the panel is resized (dragging the chat/graph splitter
    // changes the canvas size). resume-only — see the Incident Focus note above;
    // pauseAnimation would freeze pan/zoom.
    useEffect(() => {
      const fg = fgRef.current as unknown as { resumeAnimation?: () => void } | undefined;
      fg?.resumeAnimation?.();
    }, [width, height]);

    // ── Spacing forces: spread towns apart so the atlas reads clearly ───────
    // react-force-graph defaults pack nodes tightly into a central blob. Apply
    // a stronger charge + longer link distance, re-applied over ~2s because the
    // engine resets forces when graphData identity changes.
    useEffect(() => {
      const fg = fgRef.current;
      if (!fg || nodes.length === 0) return;
      let tries = 0;
      const apply = () => {
        const charge = fg.d3Force?.('charge');
        const link = fg.d3Force?.('link');
        charge?.strength?.(-620);
        link?.distance?.(130);
        link?.strength?.(0.18);
        fg.d3ReheatSimulation?.();
        if (++tries < 8) setTimeout(apply, 250);
      };
      apply();
    }, [dataVersion, nodes.length]);

    const getNodeColor = useNodeColor(nodeColorOverride);

    // ── Procedural features (recalculated when nodes move significantly) ───
    const featuresRef = useRef<MapFeatures>({ items: [], centroidX: 0, centroidY: 0, spread: 200 });
    const lastFeaturesKey = useRef('');
    const featuresPopulated = useRef(false);

    // Recompute features when the set of node IDs changes (not on every frame)
    const featuresKey = useMemo(
      () => nodes.map((n) => n.id).sort().join(','),
      [nodes],
    );
    if (featuresKey !== lastFeaturesKey.current) {
      lastFeaturesKey.current = featuresKey;
      featuresPopulated.current = false;               // reset so we re-check positions
      const result = computeMapFeatures(nodes as Array<{ id: string; x?: number; y?: number; properties: Record<string, unknown> }>);
      if (result.items.length > 0) featuresPopulated.current = true;
      featuresRef.current = result;
    }

    // ── Background: paper + grid + features ─────────────────────────────────
    const onRenderFramePre = useCallback(
      (ctx: CanvasRenderingContext2D, globalScale: number) => {
        // Lazily recompute features once the simulation has assigned positions
        if (!featuresPopulated.current && nodes.length > 0) {
          const result = computeMapFeatures(nodes as Array<{ id: string; x?: number; y?: number; properties: Record<string, unknown> }>);
          if (result.items.length > 0) {
            featuresRef.current = result;
            featuresPopulated.current = true;
          }
        }

        const canvas = ctx.canvas;
        const bounds = getViewportBounds(ctx, canvas.width, canvas.height);
        drawPaperBackground(ctx, bounds, globalScale, featuresRef.current);
      },
      [nodes],
    );

    // ── Overlay: compass, legend, paper edge (drawn in screen coords) ─
    const onRenderFramePost = useCallback(
      (ctx: CanvasRenderingContext2D, _globalScale: number) => {
        // Reset to screen coordinates
        ctx.save();
        ctx.resetTransform();
        const cw = ctx.canvas.width;
        const ch = ctx.canvas.height;
        const dpr = window.devicePixelRatio || 1;

        // Paper edge border & vignette
        drawPaperEdge(ctx, cw, ch, dpr);

        drawCompassRose(ctx, cw - 50 * dpr, ch - 60 * dpr, 28.6 * dpr);
        drawMapLegend(ctx, cw - 338, 20, incidentFocus);

        ctx.restore();
      },
      [incidentFocus],
    );

    // ── Node rendering: town markers ────────────────────────────────────────
    const nodeCanvasObject = useCallback(
      (node: GNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
        if (node.x == null || node.y == null) return;
        const rawSize = Number(node.properties?.['_size']) || 6;
        const size = rawSize * nodeScale;
        const color = getNodeColor(node.label);

        const displayField = nodeDisplayField[node.label] ?? 'id';
        const label = displayField === 'id'
          ? node.id
          : String(node.properties?.[displayField] ?? node.id);

        const isIncident = String(node.properties?.['_incident'] ?? '') === 'true';
        const isDiscounted = String(node.properties?.['_discounted'] ?? '') === 'true';
        const emphasize = incidentFocus && isIncident;
        // Discounted = examined by the agent then ruled out as unrelated. Keep
        // it visible (not dimmed) in a distinct violet so the audience sees
        // what was considered and set aside, separate from the blast radius.
        const discounted = incidentFocus && isDiscounted;
        const dim = incidentFocus && !isIncident && !isDiscounted;
        const markerColor = discounted ? '#A855F7' : color;
        // Declutter: at the fit-all default zoom only incident towns are labelled;
        // every town's callout appears once the operator zooms in (or on hover).
        const showLabel = globalScale > 1.2 || emphasize || discounted;

        drawTownMarker(ctx, node.x, node.y, size, markerColor, label, globalScale, {
          showLabel, emphasize, dim, discounted,
        });
      },
      [getNodeColor, nodeDisplayField, nodeScale, incidentFocus],
    );

    // ── Link rendering: roads ───────────────────────────────────────────────
    const linkCanvasObject = useCallback(
      (link: GLink, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const src = link.source as GNode;
        const tgt = link.target as GNode;
        if (src.x == null || tgt.x == null || src.y == null || tgt.y == null) return;

        const rType = classifyRoad(link.label);
        const style = ROAD_STYLES[rType] ?? ROAD_STYLES.default;
        const seed = typeof link.id === 'string' ? hashStrLocal(link.id) : (link.id as number ?? 0);

        const bothIncident = String(src.properties?.['_incident'] ?? '') === 'true'
          && String(tgt.properties?.['_incident'] ?? '') === 'true';
        const emphasize = incidentFocus && bothIncident;
        const dim = incidentFocus && !bothIncident;

        if (dim) ctx.globalAlpha = 0.18;
        drawRoad(ctx, src.x, src.y, tgt.x, tgt.y, style, globalScale, seed, emphasize);
        ctx.globalAlpha = 1;

        // Road label (road code like "M4") — declutter at fit-all zoom; incident
        // roads stay labelled so the blast path is always legible.
        if (!dim && (globalScale > 1.4 || emphasize)) {
          const code = roadCode(typeof link.id === 'string' ? link.id : String(link.id ?? ''), rType);
          drawRoadLabel(ctx, src.x, src.y, tgt.x, tgt.y, code, globalScale, seed);
        }
      },
      [incidentFocus],
    );

    // ── Event handlers ──────────────────────────────────────────────────────
    const handleNodeHoverInternal = useCallback(
      (node: GNode | null) => onNodeHover(node as TopologyNode | null),
      [onNodeHover],
    );
    const handleLinkHoverInternal = useCallback(
      (link: GLink | null) => onLinkHover(link as TopologyEdge | null),
      [onLinkHover],
    );
    const handleNodeDoubleClick = useCallback((node: GNode) => {
      onNodeSelect?.(node);
      fgRef.current?.centerAt(node.x, node.y, 600);
      fgRef.current?.zoom(4, 600);
    }, [onNodeSelect]);

    // ── Compute paper dimensions ────────────────────────────────────────
    const paperW = flat ? width : (() => {
      const pad = 48;
      const maxAspect = 16 / 10;
      const availW = width - pad;
      const availH = height - pad;
      return Math.min(availW, availH * maxAspect);
    })();
    const paperH = flat ? height : height - 48;

    // ── 3D paper perspective styles ──────────────────────────────────────────
    const perspectiveOuter: CSSProperties = {
      width,
      height,
      perspective: flat ? 'none' : '1400px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
      background: 'linear-gradient(135deg, #e8e4df 0%, #d5d0c8 40%, #c9c3ba 100%)',
    };

    const paperInner: CSSProperties = {
      width: paperW,
      height: paperH,
      transform: flat ? 'none' : 'rotateX(28deg) rotateZ(-1.5deg)',
      transformStyle: flat ? undefined : 'preserve-3d',
      borderRadius: '4px',
      border: '3px solid #C8BFA8',
      boxShadow: [
        '0 30px 60px rgba(0,0,0,0.28)',
        '0 12px 24px rgba(0,0,0,0.18)',
        '0 4px 8px rgba(0,0,0,0.10)',
        'inset 0 0 0 1px rgba(255,255,255,0.35)',
      ].join(', '),
      overflow: 'hidden',
      touchAction: 'none',
      position: 'relative',
    };

    // ── Patch getBoundingClientRect to fix pointer offset under 3D transform ──
    // CSS 3D transforms distort getBoundingClientRect(). Both d3-zoom/d3-drag
    // (on the canvas) and force-graph's own pointer tracking (on its container
    // div) rely on BCR for coordinate math. We override BCR on every relevant
    // element inside the paper, deriving the "true" untransformed rect from
    // the outer flex container.
    const outerRef = useRef<HTMLDivElement>(null);
    const paperRef = useRef<HTMLDivElement>(null);
    const paperDims = useRef({ w: paperW, h: paperH });
    paperDims.current = { w: paperW, h: paperH };

    useEffect(() => {
      // The BCR override only exists to undo CSS-3D-transform distortion of
      // getBoundingClientRect. In flat mode there is NO transform, so the
      // native BCR is exact — patching it there feeds d3-zoom/drag slightly
      // wrong rects (off by the paper border), making pan/zoom sluggish and
      // unresponsive. Skip the patch entirely when flat.
      if (flat) return;
      const outerEl = outerRef.current;
      const paperEl = paperRef.current;
      if (!outerEl || !paperEl) return;

      const patched = new Set<Element>();
      const origBCR = Element.prototype.getBoundingClientRect;

      const fakeBCR = function (this: Element) {
        const parentRect = origBCR.call(outerEl);
        const { w, h } = paperDims.current;
        const left = parentRect.left + (parentRect.width - w) / 2;
        const top = parentRect.top + (parentRect.height - h) / 2;
        return new DOMRect(left, top, w, h);
      };

      const patchAll = () => {
        // Patch the paper div, the force-graph-container div, and the canvas
        const targets = [paperEl, ...Array.from(paperEl.querySelectorAll('div, canvas'))];
        for (const el of targets) {
          if (patched.has(el)) continue;
          patched.add(el);
          el.getBoundingClientRect = fakeBCR;
        }
      };

      // Patch now + watch for elements force-graph creates asynchronously
      patchAll();
      const observer = new MutationObserver(patchAll);
      observer.observe(paperEl, { childList: true, subtree: true });

      return () => {
        observer.disconnect();
        for (const el of patched) {
          el.getBoundingClientRect = origBCR;
        }
      };
    }, [flat]);

    // ── Zoom handlers ─────────────────────────────────────────────────────
    const handleZoomIn = useCallback(() => {
      const fg = fgRef.current;
      if (!fg) return;
      const k = (fg as unknown as { zoom(): number }).zoom();
      (fg as unknown as { zoom(k: number, ms: number): void }).zoom(k * 1.5, 400);
    }, []);

    const handleZoomOut = useCallback(() => {
      const fg = fgRef.current;
      if (!fg) return;
      const k = (fg as unknown as { zoom(): number }).zoom();
      (fg as unknown as { zoom(k: number, ms: number): void }).zoom(k / 1.5, 400);
    }, []);

    return (
      <div
        ref={outerRef}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        style={perspectiveOuter}
      >
        <div ref={paperRef} style={paperInner}>
          <ForceGraph2D
            ref={fgRef}
            width={paperW}
            height={paperH}
            graphData={{ nodes: nodes as GNode[], links: edges as GLink[] }}
            backgroundColor="transparent"
            /* ──── custom renderers ──── */
            onRenderFramePre={onRenderFramePre}
            onRenderFramePost={onRenderFramePost}
            nodeCanvasObject={nodeCanvasObject}
            nodeCanvasObjectMode={() => 'replace'}
            linkCanvasObject={linkCanvasObject}
            linkCanvasObjectMode={() => 'replace'}
            nodeId="id"
            linkSource="source"
            linkTarget="target"
            /* Hide default link rendering */
            linkWidth={0}
            linkDirectionalArrowLength={0}
            /* ──── interaction ──── */
            onNodeHover={handleNodeHoverInternal}
            onLinkHover={handleLinkHoverInternal}
            onNodeRightClick={onNodeRightClick as (node: GNode, event: MouseEvent) => void}
            onNodeClick={handleNodeDoubleClick}
            onBackgroundClick={onBackgroundClick}
            /* ──── physics ──── */
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.28}
            cooldownTicks={frozen ? 0 : Infinity}
            cooldownTime={4000}
            onEngineStop={() => {
              if (hasFitRef.current) return;
              hasFitRef.current = true;
              fgRef.current?.zoomToFit(500, flat ? 14 : 60);
            }}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            /* Custom node/link renderers depend on the zoom level (labels-on-zoom,
               incident emphasis). With autoPauseRedraw=true (default) the canvas
               skips redraws when the engine is idle, so pan/zoom updates the
               transform but never repaints — navigation looks frozen. Force a
               redraw every frame. */
            autoPauseRedraw={false}
          />
          {/* ── Zoom controls ─────────────────────────────────────────── */}
          <div
            style={{
              position: 'absolute',
              left: 14,
              bottom: 14,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
              zIndex: 10,
            }}
          >
            {[
              { label: '+', handler: handleZoomIn },
              { label: '\u2212', handler: handleZoomOut },   /* minus sign */
            ].map(({ label, handler }) => (
              <button
                key={label}
                onClick={handler}
                style={{
                  width: 30,
                  height: 30,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 18,
                  fontWeight: 600,
                  lineHeight: 1,
                  color: '#4a4640',
                  background: 'rgba(255,255,255,0.55)',
                  backdropFilter: 'blur(4px)',
                  border: '1px solid rgba(0,0,0,0.15)',
                  borderRadius: 4,
                  cursor: 'pointer',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.12)',
                  padding: 0,
                  userSelect: 'none',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.8)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.55)'; }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  },
);

/* local hash to avoid importing from mapRendering for a tiny helper */
function hashStrLocal(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}
