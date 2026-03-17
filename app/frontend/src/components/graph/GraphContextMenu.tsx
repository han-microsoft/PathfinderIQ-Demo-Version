/**
 * @module GraphContextMenu
 *
 * Right-click context menu for graph nodes — a floating menu that
 * appears on `contextmenu` events over a topology node.
 *
 * Displays the node ID and label in a header, followed by a
 * “Display Field” section listing all available property keys
 * (including `id`). Clicking a key sets it as the label text for
 * all nodes of that type via `onSetDisplayField(label, field)`.
 *
 * Uses `framer-motion` for a quick scale-in animation. A fixed
 * backdrop overlay captures clicks to dismiss the menu.
 *
 * @props
 *   - `menu`              — current menu state (x, y, node) or null to hide
 *   - `onClose`           — callback to dismiss the menu
 *   - `onSetDisplayField` — callback(label, field) to change node display text
 *
 * @collaborators
 *   - `framer-motion` (motion.div) — enter animation
 *
 * @dependents
 *   Rendered by {@link GraphTopologyViewer} overlaying the canvas.
 */
import { motion } from 'framer-motion';
import type { TopologyNode } from './useTopology';

interface GraphContextMenuProps {
  menu: { x: number; y: number; node: TopologyNode } | null;
  onClose: () => void;
  onSetDisplayField: (label: string, field: string) => void;
}

export function GraphContextMenu({ menu, onClose, onSetDisplayField }: GraphContextMenuProps) {
  if (!menu) return null;

  const nodeProperties = menu.node.properties ?? {};
  const propertyKeys = ['id', ...Object.keys(nodeProperties)];

  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} onContextMenu={(e) => {e.preventDefault(); onClose();}} />

      <motion.div
        className="fixed z-50 bg-neutral-bg3 border border-border-strong rounded-lg shadow-xl
                   py-1 min-w-[180px]"
        style={{ left: menu.x, top: menu.y }}
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.12 }}
      >
        <div className="px-3 py-1.5 border-b border-border">
          <span className="text-xs font-semibold text-text-primary">{menu.node.id}</span>
          <span className="text-[10px] text-text-muted ml-2">{menu.node.label}</span>
        </div>

        <div className="px-3 py-1.5">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">Display Field</span>
          <div className="mt-1 space-y-0.5">
            {propertyKeys.map((key) => (
              <button
                key={key}
                className="block w-full text-left text-xs px-2 py-1 rounded
                           hover:bg-neutral-bg4 text-text-secondary hover:text-text-primary"
                onClick={() => { onSetDisplayField(menu.node.label, key); onClose(); }}
              >
                {key}
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </>
  );
}
