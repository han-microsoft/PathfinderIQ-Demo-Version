/**
 * @module chatSettingsStore
 *
 * Lightweight Zustand store for chat and UI display preferences.
 *
 * Purpose:
 *   Holds user-adjustable settings that affect how chat messages and
 *   the overall UI are rendered.  Persisted to localStorage so
 *   preferences survive page reloads.
 *
 * State:
 *   - ``fontSizeStep`` — integer offset from the base chat font size
 *     (0 = default).  Applied to message bubbles and tool results.
 *   - ``uiScale`` — float multiplier (0.7–1.5) applied as CSS ``zoom``
 *     on the root app element, scaling the entire interface.
 *
 * Collaborators:
 *   - ChatInput.tsx      — renders the aA-/aA+ buttons
 *   - MessageBubble.tsx  — reads fontSizeStep for inline fontSize
 *   - Header.tsx         — renders the UI scale slider
 *   - App.tsx            — reads uiScale and applies CSS zoom
 *
 * Dependents:
 *   Consumed by chat/layout components.
 */

import { create } from "zustand";

/** Maps fontSizeStep offsets to Tailwind-compatible rem values. */
export const FONT_SIZE_MAP: Record<number, string> = {
  [-3]: "0.65rem",
  [-2]: "0.725rem",
  [-1]: "0.8rem",
  [0]:  "0.875rem",
  [1]:  "1rem",
  [2]:  "1.125rem",
  [3]:  "1.25rem",
  [4]:  "1.5rem",
};

const MIN_STEP = -3;
const MAX_STEP = 4;
export { MIN_STEP, MAX_STEP };
const MIN_SCALE = 0.7;
const MAX_SCALE = 1.5;
const DEFAULT_SCALE = 1.1;
const MIN_CHAT_TEXT = 10;
const MAX_CHAT_TEXT = 300;
const DEFAULT_CHAT_TEXT = 100;
export { MIN_CHAT_TEXT, MAX_CHAT_TEXT };

interface ChatSettingsState {
  fontSizeStep: number;
  uiScale: number;
  chatTextScale: number;  // percentage 10-300, default 100
  obsFontSizeStep: number;
  graphVisible: boolean;
  contextDepth: number | null;  // null = unlimited, positive int = max turns
  increaseFontSize: () => void;
  decreaseFontSize: () => void;
  setFontSizeStep: (step: number) => void;
  setUiScale: (scale: number) => void;
  setChatTextScale: (pct: number) => void;
  increaseObsFontSize: () => void;
  decreaseObsFontSize: () => void;
  toggleGraph: () => void;
  setContextDepth: (depth: number | null) => void;
}

function loadStep(): number {
  try {
    const raw = localStorage.getItem("chat-font-step");
    if (raw !== null) {
      const n = parseInt(raw, 10);
      if (!isNaN(n) && n >= MIN_STEP && n <= MAX_STEP) return n;
    }
  } catch { /* ignore */ }
  return 0;
}

function saveStep(step: number): void {
  try { localStorage.setItem("chat-font-step", String(step)); } catch { /* ignore */ }
}

function loadScale(): number {
  try {
    const raw = localStorage.getItem("ui-scale");
    if (raw !== null) {
      const n = parseFloat(raw);
      if (!isNaN(n) && n >= MIN_SCALE && n <= MAX_SCALE) return n;
    }
  } catch { /* ignore */ }
  return DEFAULT_SCALE;
}

function saveScale(scale: number): void {
  try { localStorage.setItem("ui-scale", String(scale)); } catch { /* ignore */ }
}

function loadObsStep(): number {
  try {
    const raw = localStorage.getItem("obs-font-step");
    if (raw !== null) {
      const n = parseInt(raw, 10);
      if (!isNaN(n) && n >= MIN_STEP && n <= MAX_STEP) return n;
    }
  } catch { /* ignore */ }
  return 3; // Default to step 3 (1.25rem) — roughly 2-3x the tiny default
}

function saveObsStep(step: number): void {
  try { localStorage.setItem("obs-font-step", String(step)); } catch { /* ignore */ }
}

export const useChatSettingsStore = create<ChatSettingsState>((set) => ({
  fontSizeStep: loadStep(),
  uiScale: loadScale(),
  chatTextScale: (() => {
    try {
      const raw = localStorage.getItem("chat-text-scale");
      if (raw !== null) { const n = parseInt(raw, 10); if (n >= MIN_CHAT_TEXT && n <= MAX_CHAT_TEXT) return n; }
    } catch { /* ignore */ }
    return DEFAULT_CHAT_TEXT;
  })(),
  obsFontSizeStep: loadObsStep(),
  graphVisible: localStorage.getItem("graph-visible") !== "false",
  contextDepth: (() => {
    try {
      const raw = localStorage.getItem("context-depth");
      if (raw !== null) {
        const n = parseInt(raw, 10);
        if (!isNaN(n) && n > 0 && n <= 50) return n;
      }
    } catch { /* ignore */ }
    return null;  // unlimited by default
  })(),

  increaseFontSize: () =>
    set((s) => {
      const next = Math.min(s.fontSizeStep + 1, MAX_STEP);
      saveStep(next);
      return { fontSizeStep: next };
    }),

  decreaseFontSize: () =>
    set((s) => {
      const next = Math.max(s.fontSizeStep - 1, MIN_STEP);
      saveStep(next);
      return { fontSizeStep: next };
    }),

  setFontSizeStep: (step: number) =>
    set(() => {
      const clamped = Math.max(MIN_STEP, Math.min(MAX_STEP, Math.round(step)));
      saveStep(clamped);
      return { fontSizeStep: clamped };
    }),

  setUiScale: (scale: number) =>
    set(() => {
      const clamped = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.round(scale * 20) / 20));
      saveScale(clamped);
      return { uiScale: clamped };
    }),

  setChatTextScale: (pct: number) =>
    set(() => {
      const clamped = Math.max(MIN_CHAT_TEXT, Math.min(MAX_CHAT_TEXT, Math.round(pct)));
      try { localStorage.setItem("chat-text-scale", String(clamped)); } catch { /* ignore */ }
      return { chatTextScale: clamped };
    }),

  increaseObsFontSize: () =>
    set((s) => {
      const next = Math.min(s.obsFontSizeStep + 1, MAX_STEP);
      saveObsStep(next);
      return { obsFontSizeStep: next };
    }),

  decreaseObsFontSize: () =>
    set((s) => {
      const next = Math.max(s.obsFontSizeStep - 1, MIN_STEP);
      saveObsStep(next);
      return { obsFontSizeStep: next };
    }),

  toggleGraph: () =>
    set((s) => {
      const next = !s.graphVisible;
      try { localStorage.setItem("graph-visible", String(next)); } catch { /* ignore */ }
      return { graphVisible: next };
    }),

  setContextDepth: (depth: number | null) =>
    set(() => {
      try {
        if (depth === null || depth <= 0) {
          localStorage.removeItem("context-depth");
        } else {
          localStorage.setItem("context-depth", String(Math.min(50, depth)));
        }
      } catch { /* ignore */ }
      return { contextDepth: depth && depth > 0 ? Math.min(50, depth) : null };
    }),
}));
