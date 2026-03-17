/**
 * Console interceptor — captures browser console.* calls and POSTs them
 * to the backend observability endpoint for SSE streaming.
 *
 * Purpose:
 *   Monkey-patches ``console.log``, ``console.info``, ``console.warn``,
 *   ``console.error``, and ``console.debug`` to forward each call to
 *   ``POST /observability/logs/frontend``.  The original console methods
 *   are preserved and always invoked first so dev-tools output is unaffected.
 *
 * Architecture:
 *   Browser console.* → interceptor → POST /observability/logs/frontend
 *     → LogBroadcaster.broadcast() → SSE /observability/logs/frontend
 *     → useLogStream hook → LogStream component (Frontend tab)
 *
 * Key collaborators:
 *   - ``router_observability.py`` — receives POSTed entries
 *   - ``log_broadcaster.py``     — fans out to SSE subscribers
 *   - ``TabbedLogStream.tsx``    — renders the Frontend tab
 *
 * Dependents:
 *   Called by: ``main.tsx`` at application startup (one-time init)
 */

/** Map browser console method names to log level strings matching the backend format. */
const LEVEL_MAP: Record<string, string> = {
  log: "INFO",
  info: "INFO",
  warn: "WARNING",
  error: "ERROR",
  debug: "DEBUG",
};

/** Console methods to intercept. */
const METHODS = ["log", "info", "warn", "error", "debug"] as const;

import { BASE } from "@/foundation/constants";

/** Resolved base URL for the backend API (cached once at init time). */
let _baseUrl = "";

/** Guard flag — prevents re-initialisation if called more than once. */
let _installed = false;

/**
 * Serialise console arguments into a single message string.
 *
 * Handles primitives, objects, arrays, and Error instances.
 * Mirrors ``console`` output format as closely as practical.
 *
 * @param args - The variadic arguments passed to the console method.
 * @returns A single string representation of all arguments.
 */
function argsToString(args: unknown[]): string {
  return args
    .map((a) => {
      if (a instanceof Error) {
        /* Include stack trace for Error objects — critical for debugging */
        return `${a.name}: ${a.message}${a.stack ? `\n${a.stack}` : ""}`;
      }
      if (typeof a === "object" && a !== null) {
        try {
          return JSON.stringify(a, null, 0);
        } catch {
          /* Circular reference or non-serialisable — fall back to toString */
          return String(a);
        }
      }
      return String(a);
    })
    .join(" ");
}

/**
 * Format current time as HH:MM:SS.mmm to match backend LogBroadcaster format.
 *
 * @returns Timestamp string in HH:MM:SS.mmm format.
 */
function timestamp(): string {
  const d = new Date();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  const ms = String(d.getMilliseconds()).padStart(3, "0");
  return `${hh}:${mm}:${ss}.${ms}`;
}

/**
 * POST a log entry to the backend. Entries are buffered and flushed
 * periodically (every 2s) or when the buffer reaches 50 entries —
 * whichever comes first. This replaces per-call individual POSTs
 * that caused 10+ requests in the first 500ms during page load.
 *
 * @param entry - The log entry dict matching FrontendLogEntry schema.
 */

/** Batching state — buffer + flush timer */
let _buffer: Array<{ ts: string; level: string; name: string; msg: string }> = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;
/** Flush interval — how often buffered entries are sent (ms) */
const FLUSH_INTERVAL_MS = 2000;
/** Max buffer size — triggers an immediate flush when reached */
const MAX_BUFFER = 50;

/** Send the buffered entries as a JSON array and reset the buffer. */
function _flush(): void {
  if (_buffer.length === 0) return;
  const batch = _buffer;
  _buffer = [];
  _flushTimer = null;
  fetch(`${_baseUrl}/observability/logs/frontend/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(batch),
    keepalive: true,
  }).catch(() => {
    /* Swallow errors — logging failures must never trigger more console calls */
  });
}

function sendEntry(entry: {
  ts: string;
  level: string;
  name: string;
  msg: string;
}): void {
  _buffer.push(entry);
  if (_buffer.length >= MAX_BUFFER) {
    _flush();
  } else if (!_flushTimer) {
    _flushTimer = setTimeout(_flush, FLUSH_INTERVAL_MS);
  }
}

/**
 * Install the console interceptor. Monkey-patches console.log/info/warn/error/debug
 * to forward captured output to the backend observability endpoint.
 *
 * Must be called once at application startup (e.g., in main.tsx).
 * Subsequent calls are no-ops (idempotent).
 *
 * Side effects:
 *   - Replaces global console methods with wrapper functions.
 *   - Original methods are preserved and called first — dev-tools output is unaffected.
 *   - Sends HTTP POST for each console call (fire-and-forget).
 *
 * Dependencies:
 *   - VITE_API_URL env var for backend URL resolution.
 */
export function installConsoleInterceptor(): void {
  /* Idempotent guard — safe to call multiple times */
  if (_installed) return;
  _installed = true;

  /* Resolve backend base URL from the shared constant */
  _baseUrl = BASE;

  for (const method of METHODS) {
    /* Capture the original console method before patching */
    const original = console[method].bind(console);

    /* Replace with intercepting wrapper */
    console[method] = (...args: unknown[]) => {
      /* Always call the original first — dev-tools must not be disrupted */
      original(...args);

      /* Build log entry matching the backend FrontendLogEntry schema */
      const entry = {
        ts: timestamp(),
        level: LEVEL_MAP[method],
        name: `console.${method}`,
        msg: argsToString(args),
      };

      /* Fire-and-forget POST to the backend */
      sendEntry(entry);
    };
  }
}
