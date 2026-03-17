/**
 * @module GraphEdgeToolbar
 *
 * Edge type filter toolbar — a horizontal strip of toggleable edge-type
 * chips displayed below the node toolbar in the graph panel.
 *
 * Mirrors the pattern of {@link GraphToolbar} but for edges. Each chip
 * shows a colour line, the relationship label, and a click-to-toggle
 * filter. Active chips are opaque; inactive chips are muted. A count
 * badge shows visible-edge / total-edge ratio.
 *
 * Includes a colour picker popover ({@link ColorWheelPopover}) for
 * customising individual edge type colours, and a text label style
 * popover for adjusting edge label font size and colour globally.
 *
 * Uses `EDGE_COLOR_PALETTE` from {@link graphConstants} for default
 * colours, with a deterministic hash-based fallback.
 *
 * @props
 *   - `availableEdgeLabels`, `activeEdgeLabels` — all edge labels and visible set
 *   - `onToggleEdgeLabel`     — callback to toggle an edge label’s visibility
 *   - `visibleEdgeCount`, `totalEdgeCount` — counts for the summary badge
 *   - `edgeColorOverride`     — per-label colour overrides
 *   - `onSetEdgeColor`        — callback to persist a new colour for an edge label
 *   - `edgeLabelFontSize`, `onEdgeLabelFontSizeChange` — global edge label font size
 *   - `edgeLabelColor`, `onEdgeLabelColorChange` — global edge label colour
 *
 * @collaborators
 *   - {@link ColorWheelPopover} — HSL colour picker for edge type customisation
 *   - {@link graphConstants}    — COLOR_PALETTE, EDGE_COLOR_PALETTE
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer} when `showEdgeBar` is true.
 */
import { ScrollableBar } from './ScrollableBar';
import { COLOR_PALETTE, EDGE_COLOR_PALETTE } from './graphConstants';

interface GraphEdgeToolbarProps {
  availableEdgeLabels: string[];
  activeEdgeLabels: string[];
  onToggleEdgeLabel: (label: string) => void;
  edgeColorOverride: Record<string, string>;
}

function getEdgeColor(label: string, overrides: Record<string, string>): string {
  if (overrides[label]) return overrides[label];
  const palette = EDGE_COLOR_PALETTE.length > 0 ? EDGE_COLOR_PALETTE : COLOR_PALETTE;
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  return palette[Math.abs(hash) % palette.length];
}

export function GraphEdgeToolbar({
  availableEdgeLabels, activeEdgeLabels, onToggleEdgeLabel,
  edgeColorOverride,
}: GraphEdgeToolbarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      <span className="text-xs font-medium text-text-muted whitespace-nowrap">━ Edges</span>

      <ScrollableBar className="flex-1 ml-1">
        {availableEdgeLabels.map((label) => {
          const active = activeEdgeLabels.length === 0 || activeEdgeLabels.includes(label);
          const color = getEdgeColor(label, edgeColorOverride);
          return (
            <span
              key={label}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs
                         border transition-colors shrink-0
                         ${active
                           ? 'border-border-strong text-text-secondary'
                           : 'border-transparent text-text-muted opacity-40'}`}
            >
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{ backgroundColor: color }}
              />
              <button
                className="hover:text-text-primary transition-colors"
                onClick={() => onToggleEdgeLabel(label)}
              >
                {label}
              </button>
            </span>
          );
        })}
      </ScrollableBar>
    </div>
  );
}
