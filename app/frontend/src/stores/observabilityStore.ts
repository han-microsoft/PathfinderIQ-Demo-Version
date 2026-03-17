/**
 * Observability store — panel visibility, active tab, metadata state.
 *
 * Purpose:
 *   Zustand store that owns all observability panel UI state: visibility
 *   toggle, active tab selection, and polled metadata from the backend.
 *
 * Isolation (CRITICAL):
 *   This store has ZERO imports from chatStore or sessionStore.
 *   It does not reference any chat/session types, actions, or state.
 *   It is entirely self-contained.
 *
 * Key collaborators:
 *   - components/observability/ObservabilityPanel.tsx — reads isVisible
 *   - components/layout/Header.tsx — calls toggle()
 *
 * Dependents:
 *   Called by: ObservabilityPanel, Header, MetadataDashboard
 */

import { create } from "zustand";

/** Shape of the /api/observability/status response. */
export interface ObservabilityStatus {
  last_run: {
    model: string;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    duration_ms: number;
    tool_calls: number;
    thread_id: string;
  };
  fabric: {
    state: string;
    consecutive_429s: number;
    cooldown_s: number;
    semaphore_available: number;
  } | null;
}

/** Active tab in the observability panel. */
export type ObsTab = "agent" | "frontend" | "backend";

interface ObservabilityState {
  /** Whether the observability panel is visible. */
  isVisible: boolean;
  /** Currently active tab. */
  activeTab: ObsTab;
  /** Last polled status snapshot from /api/observability/status. */
  status: ObservabilityStatus | null;
  /** Whether status is currently being fetched. */
  statusLoading: boolean;

  /** Toggle panel visibility. */
  toggle: () => void;
  /** Set active tab. */
  setTab: (tab: ObsTab) => void;
  /** Fetch status from the backend. */
  fetchStatus: () => Promise<void>;
}

export const useObservabilityStore = create<ObservabilityState>((set) => ({
  /* Default: hidden, agent tab selected */
  isVisible: false,
  activeTab: "agent",
  status: null,
  statusLoading: false,

  toggle: () => set((s) => ({ isVisible: !s.isVisible })),

  setTab: (tab) => set({ activeTab: tab }),

  fetchStatus: async () => {
    set({ statusLoading: true });
    try {
      const { getObservabilityStatus } = await import("@/api/platformApi");
      const data = await getObservabilityStatus() as unknown as ObservabilityStatus;
      set({ status: data, statusLoading: false });
    } catch {
      /* Fail-silent: observability errors must not affect chat. */
      set({ statusLoading: false });
    }
  },
}));
