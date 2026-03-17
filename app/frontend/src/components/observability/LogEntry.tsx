/**
 * LogEntry — single log line renderer with level-based coloring.
 *
 * Purpose:
 *   Renders one log entry as a compact, color-coded line inside the
 *   observability log stream.  Purely presentational — no state, no
 *   side effects.
 *
 * Isolation:
 *   No imports from chat, session, or any store.
 *
 * Dependents:
 *   Called by: LogStream.tsx
 */

import type { LogEntry as LogEntryType } from "./useLogStream";

/** Map log levels to Tailwind text color classes. */
const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-gray-400",
  INFO: "text-status-success",
  WARNING: "text-status-warning",
  ERROR: "text-status-error",
};

interface LogEntryProps {
  /** The log entry data from the backend. */
  entry: LogEntryType;
}

/**
 * Render a single log line: [timestamp] [LEVEL] [logger] message.
 *
 * Color-coded by level for quick visual scanning.
 */
export function LogEntryLine({ entry }: LogEntryProps) {
  /* Resolve color class for the log level, default to neutral gray */
  const levelColor = LEVEL_COLORS[entry.level] ?? "text-text-muted";

  return (
    <div className="flex gap-2 px-3 py-0.5 font-mono leading-5 hover:bg-neutral-bg3/50">
      {/* Timestamp — fixed width for alignment */}
      <span className="text-text-muted shrink-0 w-[72px]">{entry.ts}</span>
      {/* Level badge — fixed width, color-coded */}
      <span className={`shrink-0 w-[52px] font-medium ${levelColor}`}>
        {entry.level}
      </span>
      {/* Logger name — truncated */}
      <span className="text-text-muted shrink-0 w-[160px] truncate">
        {entry.name}
      </span>
      {/* Message — fills remaining space, wraps if needed */}
      <span className="text-text-primary break-all">{entry.msg}</span>
    </div>
  );
}
