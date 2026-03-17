/**
 * LogStream — SSE log stream renderer with level filtering and auto-scroll.
 *
 * Purpose:
 *   Connects to a backend SSE log endpoint via ``useLogStream`` and renders
 *   a scrollable list of color-coded log entries.  Provides level-based
 *   filtering and a search box for message text filtering.
 *
 * Isolation:
 *   No imports from chat, session, chatStore, or sessionStore.
 *   Uses its own scroll logic (not useAutoScroll from the chat domain).
 *
 * Key collaborators:
 *   - hooks/useLogStream.ts — SSE connection + rolling buffer
 *   - LogEntry.tsx — renders individual log lines
 *
 * Dependents:
 *   Called by: TabbedLogStream.tsx
 */

import { useRef, useEffect, useState, useCallback } from "react";
import { useLogStream, type StreamStatus } from "./useLogStream";
import { LogEntryLine } from "./LogEntry";

/** Log levels available for filtering. */
const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"] as const;

interface LogStreamProps {
  /** SSE endpoint URL (e.g., "/api/observability/logs/agent"). */
  url: string;
  /** Whether this stream should be active (connected). */
  enabled: boolean;
}

/**
 * SSE log stream with level filtering, text search, and auto-scroll.
 *
 * Auto-scrolls to bottom on new entries unless the user has scrolled up
 * (pause-on-scroll pattern).  This is independent of the chat domain's
 * useAutoScroll hook.
 */
export function LogStream({ url, enabled }: LogStreamProps) {
  const { entries, status, clear } = useLogStream({ url, enabled });
  /* Level filter: which levels to show (all by default) */
  const [activeLevels, setActiveLevels] = useState<Set<string>>(
    new Set(LEVELS)
  );
  /* Text search filter */
  const [search, setSearch] = useState("");
  /* Auto-scroll state: true = follow tail, false = user scrolled up */
  const [autoScroll, setAutoScroll] = useState(true);
  /* Scroll container ref */
  const containerRef = useRef<HTMLDivElement>(null);

  /** Toggle a log level in the filter set. */
  const toggleLevel = useCallback((level: string) => {
    setActiveLevels((prev) => {
      const next = new Set(prev);
      if (next.has(level)) next.delete(level);
      else next.add(level);
      return next;
    });
  }, []);

  /** Detect user scroll-up to pause auto-scroll. */
  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    /* Consider "at bottom" if within 40px of the scroll end */
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }, []);

  /** Auto-scroll to bottom when new entries arrive (if not paused). */
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  /* Apply level + search filters */
  const searchLower = search.toLowerCase();
  const filtered = entries.filter(
    (e) =>
      activeLevels.has(e.level) &&
      (search === "" || e.msg.toLowerCase().includes(searchLower))
  );

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar: status indicator + level filters + search + clear */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-neutral-bg2">
        {/* Connection status dot */}
        <StatusDot status={status} />

        {/* Level filter toggles */}
        {LEVELS.map((lvl) => (
          <button
            key={lvl}
            onClick={() => toggleLevel(lvl)}
            className={`px-1.5 py-0.5 rounded border font-medium transition-colors ${
              activeLevels.has(lvl)
                ? "border-brand/40 bg-brand/10 text-brand"
                : "border-border text-text-muted opacity-50"
            }`}
          >
            {lvl}
          </button>
        ))}

        {/* Search input */}
        <input
          type="text"
          placeholder="Filter…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="ml-auto w-32 px-2 py-0.5 rounded border border-border bg-neutral-bg1 text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand/50"
        />

        {/* Clear button */}
        <button
          onClick={clear}
          className="px-1.5 py-0.5 rounded border border-border text-text-muted hover:text-text-primary hover:bg-neutral-bg3 transition-colors"
        >
          Clear
        </button>

        {/* Entry count */}
        <span className="text-text-muted">{filtered.length}</span>
      </div>

      {/* Log entries — scrollable container */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden"
      >
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-muted text-xs">
            {status === "disconnected"
              ? "Disconnected — retrying…"
              : "No log entries"}
          </div>
        ) : (
          filtered.map((entry, i) => <LogEntryLine key={i} entry={entry} />)
        )}
      </div>

      {/* Scroll-to-bottom indicator (shown when paused) */}
      {!autoScroll && filtered.length > 0 && (
        <button
          onClick={() => {
            setAutoScroll(true);
            if (containerRef.current) {
              containerRef.current.scrollTop =
                containerRef.current.scrollHeight;
            }
          }}
          className="absolute bottom-2 right-4 px-2 py-1 rounded bg-brand/90 text-white shadow-lg hover:bg-brand transition-colors"
        >
          ↓ Follow
        </button>
      )}
    </div>
  );
}

/** Small colored dot indicating SSE connection status. */
function StatusDot({ status }: { status: StreamStatus }) {
  const color =
    status === "connected"
      ? "bg-status-success"
      : status === "connecting"
        ? "bg-status-warning animate-pulse"
        : "bg-status-error";

  return (
    <span
      className={`inline-block w-1.5 h-1.5 rounded-full ${color}`}
      title={status}
    />
  );
}
