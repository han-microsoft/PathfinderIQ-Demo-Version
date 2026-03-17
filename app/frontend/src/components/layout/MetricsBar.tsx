/**
 * @module MetricsBar
 *
 * Graph panel host — a full-height container that measures its own
 * dimensions via `ResizeObserver` and passes pixel-accurate width/height
 * to the embedded {@link GraphTopologyViewer}.
 *
 * The observer fires on every resize (including the parent
 * {@link ResizableGraph} drag), ensuring the force-graph canvas always
 * fills its container without overflow or blank space.
 *
 * @remarks
 * - No props — self-contained with internal size state.
 *
 * @collaborators
 *   - {@link GraphTopologyViewer} — rendered child, receives width/height
 *   - `ResizeObserver` (Web API)   — monitors container dimensions
 *
 * @dependents
 *   Rendered by {@link ResizableGraph} as the content inside
 *   the resizable region.
 */
import { useRef, useState, useEffect } from 'react';
import { GraphTopologyViewer } from '../graph/GraphTopologyViewer';
export function MetricsBar() {
  const graphPanelRef = useRef<HTMLDivElement>(null);
  const [graphSize, setGraphSize] = useState({ width: 800, height: 300 });

  useEffect(() => {
    const el = graphPanelRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      setGraphSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={graphPanelRef} className="h-full">
      <GraphTopologyViewer width={graphSize.width} height={graphSize.height} />
    </div>
  );
}
