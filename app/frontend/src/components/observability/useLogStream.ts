/**
 * useLogStream — EventSource hook for SSE log streaming with rolling buffer.
 *
 * Purpose:
 *   Connects to an SSE endpoint (``/api/observability/logs/*``) and maintains
 *   a rolling buffer of log entries.  Handles auto-reconnect on disconnect
 *   and provides pause/resume control for scroll-back.
 *
 * Isolation:
 *   This hook is entirely independent of chat SSE (``api/client.ts``),
 *   ``chatStore``, and ``sessionStore``.  It opens its own ``EventSource``
 *   connection to observability-specific endpoints only.
 *
 * Key collaborators:
 *   - ``components/observability/LogStream.tsx`` — primary consumer
 *
 * Dependents:
 *   Called by: ``LogStream.tsx``
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { getAccessToken } from "@/auth";

/** Shape of a single log entry from the backend LogBroadcaster. */
export interface LogEntry {
  /** Timestamp string (HH:MM:SS.mmm) from the backend. */
  ts: string;
  /** Log level: DEBUG, INFO, WARNING, ERROR. */
  level: string;
  /** Logger name (e.g., "tools.fabric.graph", "app.services.llm_agent"). */
  name: string;
  /** Formatted log message text. */
  msg: string;
}

/** Connection state for the EventSource. */
export type StreamStatus = "connecting" | "connected" | "disconnected";

/** Maximum number of log entries retained in the rolling buffer. */
const MAX_BUFFER = 200;

/** Delay (ms) before attempting reconnect after disconnect. */
const RECONNECT_DELAY = 3000;

interface UseLogStreamOptions {
  /** SSE endpoint URL (e.g., "/api/observability/logs/agent"). */
  url: string;
  /** Whether the stream should be active.  If false, no connection is opened. */
  enabled?: boolean;
}

interface UseLogStreamReturn {
  /** Rolling buffer of log entries (newest last). */
  entries: LogEntry[];
  /** Current connection status. */
  status: StreamStatus;
  /** Clear the log buffer. */
  clear: () => void;
}

/**
 * Hook that connects to an SSE log endpoint and maintains a rolling buffer.
 *
 * @param options - Configuration: url and enabled flag.
 * @returns entries array, connection status, and clear function.
 */
export function useLogStream({
  url,
  enabled = true,
}: UseLogStreamOptions): UseLogStreamReturn {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [status, setStatus] = useState<StreamStatus>("disconnected");
  /* Ref to the EventSource instance for cleanup */
  const esRef = useRef<EventSource | null>(null);
  /* Ref to the reconnect timer for cleanup */
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Clear the log buffer. */
  const clear = useCallback(() => setEntries([]), []);

  useEffect(() => {
    /* Do not connect if disabled or no URL */
    if (!enabled || !url) {
      setStatus("disconnected");
      return;
    }

    /** Resolve the full URL using the same base as the chat API client. */
    const baseUrl =
      (import.meta as unknown as { env?: { VITE_API_URL?: string } }).env
        ?.VITE_API_URL ?? "";
    const fullUrl = `${baseUrl}${url}`;

    /** Open EventSource connection with auth token query param. */
    const connect = async () => {
      setStatus("connecting");

      // Acquire token for EventSource query param auth
      const token = await getAccessToken();
      const sep = fullUrl.includes("?") ? "&" : "?";
      const authedUrl = token
        ? `${fullUrl}${sep}token=${encodeURIComponent(token)}`
        : fullUrl;

      const es = new EventSource(authedUrl);
      esRef.current = es;

      es.onopen = () => setStatus("connected");

      /* Named event "log" — matches backend SSE format */
      es.addEventListener("log", (event: MessageEvent) => {
        try {
          const entry: LogEntry = JSON.parse(event.data);
          setEntries((prev) => {
            /* Rolling buffer: keep last MAX_BUFFER entries */
            const next = [...prev, entry];
            return next.length > MAX_BUFFER
              ? next.slice(next.length - MAX_BUFFER)
              : next;
          });
        } catch {
          /* Malformed JSON — skip silently */
        }
      });

      es.onerror = () => {
        /* EventSource fires error on disconnect or network failure */
        es.close();
        esRef.current = null;
        setStatus("disconnected");
        /* Auto-reconnect after delay — fail-silent, no chat impact */
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
      };
    };

    connect();

    /* Cleanup on unmount or dependency change */
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setStatus("disconnected");
    };
  }, [url, enabled]);

  return { entries, status, clear };
}
