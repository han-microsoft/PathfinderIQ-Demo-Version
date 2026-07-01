/**
 * NodeDetailsPanel — floating card that shows a clicked node's properties as a
 * clean, modern table. Lets the operator see exactly what an entity is.
 *
 * Rendered by GraphTopologyViewer inside the relative canvas container; opens
 * on node click (onNodeSelect), closes on the X, Escape, or background click.
 */

import { useEffect } from "react";
import { X } from "lucide-react";
import type { TopologyNode } from "@/types/graph";

interface NodeDetailsPanelProps {
  node: TopologyNode | null;
  onClose: () => void;
}

/** Turn a property key (CamelCase / snake_case) into a readable label. */
function humanize(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function NodeDetailsPanel({ node, onClose }: NodeDetailsPanelProps) {
  useEffect(() => {
    if (!node) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [node, onClose]);

  if (!node) return null;

  const props = node.properties ?? {};
  // Hide internal render hints (_size, _incident, _discounted, …).
  const entries = Object.entries(props).filter(([k]) => !k.startsWith("_"));

  return (
    <div
      className="absolute top-3 right-3 z-30 w-[320px] max-w-[calc(100%-1.5rem)]
                 rounded-xl border border-border/40 bg-neutral-bg1 shadow-2xl
                 overflow-hidden"
      role="dialog"
      aria-label={`Details for ${node.id}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-border/30">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wide text-text-muted">
            {node.label}
          </div>
          <div className="font-mono text-sm font-semibold text-text-primary break-all">
            {node.id}
          </div>
        </div>
        <button
          onClick={onClose}
          aria-label="Close node details"
          className="shrink-0 rounded-md p-1 text-text-muted hover:text-text-primary hover:bg-neutral-bg3 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Properties table */}
      <div className="max-h-[55vh] overflow-y-auto">
        {entries.length === 0 ? (
          <div className="px-4 py-3 text-xs text-text-muted">No properties.</div>
        ) : (
          <table className="w-full text-xs">
            <tbody>
              {entries.map(([k, v], i) => (
                <tr key={k} className={i % 2 ? "bg-neutral-bg3/40" : ""}>
                  <td className="align-top px-4 py-1.5 text-text-muted font-medium whitespace-nowrap">
                    {humanize(k)}
                  </td>
                  <td className="align-top px-4 py-1.5 text-text-secondary break-words font-mono">
                    {formatValue(v)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
