/**
 * HelpOverlay — domain-blind keyboard-shortcut cheat-sheet modal.
 *
 * Pure presentational + portal. The consumer owns open/close state and the
 * shortcut table (which is inherently app-specific) and injects both.
 * Renders into `document.body` so a scrollable/overflow-clipped ancestor
 * never traps the modal.
 */
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export interface Shortcut {
  keys: string[];
  label: string;
}

export interface ShortcutGroup {
  group: string;
  items: Shortcut[];
}

export interface HelpOverlayProps {
  open: boolean;
  onClose: () => void;
  shortcuts: ShortcutGroup[];
  /** Optional modal title. */
  title?: string;
}

export function HelpOverlay({ open, onClose, shortcuts, title = "Keyboard Shortcuts" }: HelpOverlayProps) {
  if (!open) return null;

  return createPortal(
    <div
      data-testid="help-overlay"
      className="fixed inset-0 z-[60] flex items-start justify-center pt-24 bg-overlay-backdrop backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-[520px] max-w-[92vw] rounded-xl border border-border bg-neutral-bg1 shadow-xl overflow-hidden"
      >
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-neutral-bg2">
          <h3 className="text-sm font-bold text-text-primary flex-1">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {shortcuts.map((g) => (
            <section key={g.group}>
              <h4 className="text-micro font-bold uppercase tracking-wider text-text-muted mb-2">
                {g.group}
              </h4>
              <ul className="space-y-1.5">
                {g.items.map((s) => (
                  <li key={s.label} className="flex items-center gap-2 text-sm">
                    <span className="flex-1 text-text-secondary">{s.label}</span>
                    <span className="flex items-center gap-1">
                      {s.keys.map((k, i) => (
                        <kbd
                          key={`${k}-${i}`}
                          className="px-1.5 py-0.5 text-micro font-mono font-bold rounded bg-neutral-bg3 border border-border text-text-primary"
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
