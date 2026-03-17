/**
 * @module GraphToolbar
 *
 * Node type filter toolbar — a horizontal strip of toggleable node-type
 * chips displayed below the graph header.
 *
 * Each chip shows a colour dot (click to customise via
 * {@link ColorWheelPopover}), the label name, and a click-to-toggle
 * filter. Active chips have a strong border; inactive chips are muted
 * at 40% opacity. A count badge shows visible-node / total-node ratio.
 *
 * Also provides a text label style popover for adjusting node label
 * font size and colour globally.
 *
 * @props
 *   - `availableLabels`, `activeLabels` — all node labels and currently visible set
 *   - `onToggleLabel`     — callback to toggle a label’s visibility
 *   - `visibleNodeCount`, `totalNodeCount` — counts for the summary badge
 *   - `nodeColorOverride` — per-label colour overrides
 *   - `onSetColor`        — callback to persist a new colour for a label
 *   - `nodeLabelFontSize`, `onNodeLabelFontSizeChange` — global label font size
 *   - `nodeLabelColor`, `onNodeLabelColorChange` — global label colour
 *
 * @collaborators
 *   - {@link useNodeColor}       — resolves label → colour
 *   - {@link ColorWheelPopover}  — HSL colour picker for node type customisation
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer} when `showNodeBar` is true.
 */
import { useNodeColor } from './useNodeColor';
import { ScrollableBar } from './ScrollableBar';

interface GraphToolbarProps {
  availableLabels: string[];
  activeLabels: string[];
  onToggleLabel: (label: string) => void;
  nodeColorOverride: Record<string, string>;
}

export function GraphToolbar({
  availableLabels, activeLabels, onToggleLabel,
  nodeColorOverride,
}: GraphToolbarProps) {
  const getColor = useNodeColor(nodeColorOverride);

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border shrink-0">
      <span className="text-xs font-medium text-text-muted whitespace-nowrap">● Nodes</span>

      <ScrollableBar className="flex-1 ml-1">
        {availableLabels.map((label) => {
          const active = activeLabels.length === 0 || activeLabels.includes(label);
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
                style={{ backgroundColor: getColor(label) }}
              />
              <button
                className="hover:text-text-primary transition-colors"
                onClick={() => onToggleLabel(label)}
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
