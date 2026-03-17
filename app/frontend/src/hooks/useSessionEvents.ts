/**
 * useSessionEvents — subscribes to the per-session SSE event bus.
 *
 * Module role:
 *   Opens an EventSource connection to GET /api/sessions/{id}/events
 *   when a session is active. Events from delegation tool calls arrive
 *   tagged with agent_id and are routed to the correct agent chat slice
 *   via chatStore.handleDelegationEvent().
 *
 *   This enables live streaming of specialist agent output into the
 *   specialist's tab during delegation tool execution.
 *
 * Key collaborators:
 *   - Backend: app/routers/sessions.py (SSE endpoint)
 *   - Backend: app/foundation/session_broadcaster.py (event source)
 *   - stores/chatStore.ts (handleDelegationEvent consumer)
 *
 * Dependents:
 *   Mounted by: ChatPanel or App.tsx
 */

import { useEffect, useRef } from "react";
import { BASE } from "@/foundation/constants";
import { useChatStore } from "@/stores/chatStore";
import { useReplayStore } from "@/stores/replayStore";
import { getAccessToken } from "@/auth";

/**
 * Subscribe to the session's delegation event bus.
 *
 * Opens an EventSource on mount (when sessionId is non-null), routes
 * events to chatStore, and closes on unmount or session change.
 * Appends ?token=<jwt> for auth when AUTH_ENABLED=true.
 *
 * @param sessionId - The active session ID, or null if none.
 */
export function useSessionEvents(sessionId: string | null) {
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    // Skip SSE connection during replay — events are injected directly by the engine
    if (!sessionId || useReplayStore.getState().mode === "playing") return;

    let cancelled = false;

    (async () => {
      // Acquire token for EventSource query param auth
      const token = await getAccessToken();
      if (cancelled) return;

      const params = token ? `?token=${encodeURIComponent(token)}` : "";
      const url = `${BASE}/sessions/${sessionId}/events${params}`;
      const es = new EventSource(url);
      esRef.current = es;

      es.addEventListener("delegation", (e: MessageEvent) => {
        try {
          const payload = JSON.parse(e.data);
          const { agent_id, event, data } = payload;
          if (agent_id && event) {
            useChatStore.getState().handleDelegationEvent(agent_id, event, data);
          }
        } catch (err) {
          console.warn("Failed to parse delegation event:", err);
        }
      });

      es.onerror = () => {
        console.warn("[useSessionEvents] EventSource error");
      };
    })();

    return () => {
      cancelled = true;
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [sessionId]);
}
