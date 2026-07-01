/**
 * agentkit-ui / stores / paletteStore — open/close state for a command
 * palette + a help overlay.
 *
 * Domain-blind. Two booleans with mutually-exclusive toggles (opening one
 * closes the other). Kept out of any app data store so the overlay
 * lifecycle never entangles with feature state.
 */
import { create } from "zustand";

interface PaletteStore {
  /** Command palette visible. */
  open: boolean;
  /** Help overlay visible. */
  helpOpen: boolean;

  openPalette: () => void;
  close: () => void;
  togglePalette: () => void;

  openHelp: () => void;
  closeHelp: () => void;
  toggleHelp: () => void;
}

export const usePaletteStore = create<PaletteStore>((set, get) => ({
  open: false,
  helpOpen: false,

  openPalette: () => set({ open: true, helpOpen: false }),
  close: () => set({ open: false }),
  togglePalette: () => set({ open: !get().open, helpOpen: false }),

  openHelp: () => set({ helpOpen: true, open: false }),
  closeHelp: () => set({ helpOpen: false }),
  toggleHelp: () => set({ helpOpen: !get().helpOpen, open: false }),
}));
