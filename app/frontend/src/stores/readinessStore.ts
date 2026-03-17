/**
 * Readiness store — tracks initialization status for the welcome overlay.
 *
 * Each init step (sessions, service health, graph, agents, interface) has
 * a status: pending → loading → complete | failed. The welcome overlay
 * subscribes to this store and transitions status indicators in real time.
 *
 * Dependents:
 *   - WelcomeOverlay.tsx — reads all status fields
 *   - App.tsx — updates status as each fetch completes
 */

import { create } from "zustand";

export type InitStatus = "pending" | "loading" | "complete" | "failed";

interface ReadinessState {
  sessions: InitStatus;
  serviceHealth: InitStatus;
  graphTopology: InitStatus;
  agents: InitStatus;
  interface: InitStatus;
  /** True when all steps are complete (or failed — don't block on failures). */
  allReady: boolean;
  /** Set status for a specific step. */
  setStatus: (key: keyof Omit<ReadinessState, "allReady" | "setStatus" | "markAllReady">, status: InitStatus) => void;
  /** Recompute allReady from current statuses. */
  markAllReady: () => void;
}

const DONE_STATES: Set<InitStatus> = new Set(["complete", "failed"]);

export const useReadinessStore = create<ReadinessState>((set, get) => ({
  sessions: "pending",
  serviceHealth: "pending",
  graphTopology: "pending",
  agents: "pending",
  interface: "pending",
  allReady: false,

  setStatus: (key, status) => {
    set({ [key]: status });
    // Auto-check if all are done after each update
    const state = { ...get(), [key]: status };
    const allDone =
      DONE_STATES.has(state.sessions) &&
      DONE_STATES.has(state.serviceHealth) &&
      DONE_STATES.has(state.graphTopology) &&
      DONE_STATES.has(state.agents) &&
      DONE_STATES.has(state.interface);
    if (allDone) set({ allReady: true });
  },

  markAllReady: () => set({ allReady: true }),
}));
