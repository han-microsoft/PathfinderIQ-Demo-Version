/**
 * workshopStore — visibility state for the "behind the build" workshop overlays.
 *
 * Two self-contained showcases, each opened from a sidebar button and rendered
 * as a full-screen overlay in App.tsx:
 *   - Ontology Studio: how source documents become the knowledge graph.
 *   - Agent Lab: how the agent team is grown + pruned under an evidence gate.
 */

import { create } from "zustand";

interface WorkshopStore {
  studioOpen: boolean;
  openStudio: () => void;
  closeStudio: () => void;
  labOpen: boolean;
  openLab: () => void;
  closeLab: () => void;
}

export const useWorkshopStore = create<WorkshopStore>((set) => ({
  studioOpen: false,
  openStudio: () => set({ studioOpen: true }),
  closeStudio: () => set({ studioOpen: false }),
  labOpen: false,
  openLab: () => set({ labOpen: true }),
  closeLab: () => set({ labOpen: false }),
}));
