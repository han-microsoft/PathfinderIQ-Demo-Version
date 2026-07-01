/**
 * @module scenarioStore
 *
 * Zustand store for the active scenario (runtime use-case swap).
 *
 * Module role:
 *   Holds the selected scenario name + the available scenario catalog.
 *   The selection persists to localStorage and is attached as the
 *   ``X-Scenario-Name`` header on every API call (see api/client.ts), so the
 *   backend resolves the matching agents/prompts/tools/datasource/topology
 *   per-request. The core backend stays constant across swaps.
 *
 * Collaborators:
 *   - api/client.ts          — reads selectedScenario for the X-Scenario-Name header
 *   - api/scenarioApi.ts     — fetchScenarios() populates the catalog
 *   - components/ScenarioSwitcher.tsx — renders the dropdown
 *
 * Swap semantics:
 *   Changing the scenario reloads the app so every scenario-scoped store
 *   (agents, topology, scenario detail, config, sessions) refetches cleanly
 *   against the newly selected pack. This guarantees a flawless swap with no
 *   stale cross-scenario state.
 */

import { create } from "zustand";

export interface ScenarioSummary {
  name: string;
  display_name: string;
  description: string;
  domain: string;
  active?: boolean;
}

const STORAGE_KEY = "selected-scenario";

/** Read the persisted scenario selection (empty = backend operator default). */
export function loadSelectedScenario(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

interface ScenarioState {
  /** Currently selected scenario name ("" = backend default). */
  selectedScenario: string;
  /** Available scenario packs from GET /api/scenarios. */
  scenarios: ScenarioSummary[];
  /** Whether the catalog has been loaded. */
  loaded: boolean;
  /** Replace the catalog (from fetchScenarios). */
  setScenarios: (scenarios: ScenarioSummary[], active: string) => void;
  /** Switch scenario: persist + reload so all scoped state refetches. */
  selectScenario: (name: string) => void;
}

export const useScenarioStore = create<ScenarioState>((set, get) => ({
  selectedScenario: loadSelectedScenario(),
  scenarios: [],
  loaded: false,
  setScenarios: (scenarios, active) => {
    // Adopt the backend's active scenario when the user hasn't pinned one.
    const current = get().selectedScenario || active || "";
    set({ scenarios, selectedScenario: current, loaded: true });
  },
  selectScenario: (name) => {
    if (name === get().selectedScenario) return;
    try { localStorage.setItem(STORAGE_KEY, name); } catch { /* ignore */ }
    set({ selectedScenario: name });
    // Hard reload guarantees a clean swap: no stale agents/topology/sessions.
    try { window.location.reload(); } catch { /* non-browser env */ }
  },
}));
