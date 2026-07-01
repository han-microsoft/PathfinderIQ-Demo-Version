/**
 * agentkit-ui / feedback / CommandPaletteBase — domain-blind ⌘K palette.
 *
 * The palette ENGINE: substring scorer, grouped filtering, keyboard nav
 * (Arrow/Enter/Esc), portal overlay. The consumer owns open/close state and
 * the command list (which is inherently app-specific) and injects both.
 *
 * Intentionally dependency-free matching (no Fuse.js/cmdk) — fast enough for
 * the ~20–50 entries a palette typically exposes.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ArrowRight } from "lucide-react";
import { createPortal } from "react-dom";

/** A single palette command. `group` is a free-form section label. */
export interface Command {
  id: string;
  label: string;
  /** Optional right-aligned hint (e.g. "Tab 1", an id). */
  hint?: string;
  /** Extra search tokens beyond the label. */
  keywords?: string[];
  /** Grouping bucket for sectioning the results list. */
  group: string;
  /** Fire-and-forget; the palette closes after invoking it. */
  run: () => void | Promise<void>;
}

export interface CommandPaletteBaseProps {
  open: boolean;
  onClose: () => void;
  commands: Command[];
  placeholder?: string;
  emptyLabel?: string;
}

/** Score a command against a query. Lower is better; -1 means no match. */
function score(cmd: Command, q: string): number {
  if (!q) return 0;
  const hay = [cmd.label, cmd.hint ?? "", ...(cmd.keywords ?? [])].join(" ").toLowerCase();
  const idx = hay.indexOf(q.toLowerCase());
  if (idx < 0) return -1;
  const labelIdx = cmd.label.toLowerCase().indexOf(q.toLowerCase());
  return labelIdx >= 0 ? labelIdx : idx + 100;
}

export function CommandPaletteBase({
  open,
  onClose,
  commands,
  placeholder = "Search commands…",
  emptyLabel = "No matching commands",
}: CommandPaletteBaseProps) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    return commands
      .map((c) => ({ cmd: c, s: score(c, query.trim()) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => a.s - b.s)
      .map((x) => x.cmd);
  }, [commands, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (cursor >= filtered.length) setCursor(0);
  }, [filtered.length, cursor]);

  if (!open) return null;

  const runAndClose = (cmd: Command) => {
    try {
      void cmd.run();
    } finally {
      onClose();
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(filtered.length - 1, c + 1)); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); return; }
    if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filtered[cursor];
      if (cmd) runAndClose(cmd);
    }
  };

  /* Group the filtered list for sectioning, preserving insertion order. */
  const groups: { name: string; items: Command[] }[] = [];
  for (const c of filtered) {
    let g = groups.find((x) => x.name === c.group);
    if (!g) { g = { name: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  }
  const flat = groups.flatMap((g) => g.items);

  return createPortal(
    <div
      data-testid="command-palette"
      className="fixed inset-0 z-[60] flex items-start justify-center pt-24 bg-overlay-backdrop backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-[560px] max-w-[92vw] rounded-xl border border-border bg-neutral-bg1 shadow-xl overflow-hidden"
      >
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2">
          <Search className="h-4 w-4 text-text-muted" />
          <input
            ref={inputRef}
            data-testid="command-palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            className="flex-1 bg-transparent outline-none text-sm text-text-primary placeholder:text-text-muted"
          />
          <span className="text-micro font-mono text-text-muted uppercase tracking-wider">Esc to close</span>
        </div>
        <div className="max-h-[50vh] overflow-y-auto py-1">
          {flat.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-text-muted">{emptyLabel}</div>
          )}
          {groups.map((g) => (
            <div key={g.name} className="py-1">
              <div className="px-3 pt-1 pb-0.5 text-micro font-bold uppercase tracking-wider text-text-muted">
                {g.name}
              </div>
              {g.items.map((cmd) => {
                const idx = flat.indexOf(cmd);
                const active = idx === cursor;
                return (
                  <button
                    key={cmd.id}
                    data-testid={`command-${cmd.id}`}
                    onMouseEnter={() => setCursor(idx)}
                    onMouseDown={(e) => { e.preventDefault(); runAndClose(cmd); }}
                    className={[
                      "w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm",
                      active ? "bg-brand/15 text-text-primary" : "text-text-secondary hover:bg-neutral-bg2",
                    ].join(" ")}
                  >
                    <ArrowRight className={`h-3 w-3 ${active ? "text-brand" : "text-text-muted"}`} />
                    <span className="flex-1 truncate">{cmd.label}</span>
                    {cmd.hint && (
                      <span className="shrink-0 text-micro font-mono text-text-muted uppercase tracking-wider">
                        {cmd.hint}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
