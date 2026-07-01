/**
 * Replay store — controls session replay playback state.
 *
 * Module role:
 *   Lightweight Zustand store that tracks whether a pre-recorded session
 *   replay is active. The replay engine reads/writes this store to
 *   coordinate playback, and UI components (ChatInput, useSessionEvents,
 *   WelcomeOverlay) read it to enable replay-mode guards.
 *
 * State machine:
 *   off → startReplay() → playing → stopReplay() → done
 *                            ↑                         ↓
 *                            └──── (re-trigger) ───────┘
 *
 * Key collaborators:
 *   - features/replay/replayEngine.ts  — drives playback, calls start/stop
 *   - stores/chatStore.ts              — receives injected streaming events
 *   - stores/agentStore.ts             — tab switching during delegation
 *   - components/layout/WelcomeOverlay — entry point for demo replay
 *   - components/chat/ChatInput        — disables input during replay
 *   - hooks/useSessionEvents           — skips real SSE during replay
 */

import { create } from "zustand";

export type ReplayMode = "off" | "playing" | "done";
export type ReplayVariant = "detailed" | "fast" | "skip";

/** Data for an in-context highlight callout during replay. */
export interface ReplayHighlightData {
  /** DOM selector target — matches data-tool-id on tool call cards. */
  targetId: string;
  /** Callout title. */
  title: string;
  /** Callout body text. */
  body: string;
}

interface ReplayStore {
  /** Current replay state. */
  mode: ReplayMode;
  /** Which scenario-owned replay variant is active. */
  replayVariant: ReplayVariant;
  /** Playback speed multiplier (1 = real-time, 2 = 2x, etc.). */
  speedMultiplier: number;
  /** Whether replay is currently waiting on tour continue. */
  isPaused: boolean;
  /** Active guided tour step index, -1 when hidden. */
  tourStepIndex: number;
  /** AbortController to cancel an in-flight replay. */
  _abortController: AbortController | null;
  /** Internal resolver used by pauseForTour/resumeTour. */
  _resumeResolver: (() => void) | null;

  /** Active highlight callout (null when none). */
  activeHighlight: ReplayHighlightData | null;
  /** Internal resolver for highlight dismiss. */
  _highlightResolver: (() => void) | null;

  /** Begin a replay session. */
  startReplay: (variant?: ReplayVariant) => void;
  /** Mark replay as finished. */
  stopReplay: () => void;
  /** Cancel an in-progress replay and reset to off. */
  cancelReplay: () => void;
  /** Adjust playback speed. */
  setSpeed: (multiplier: number) => void;
  /** Pause replay and wait for guided-tour continue action. */
  pauseForTour: (stepIndex: number) => Promise<void>;
  /** Resume replay from current guided-tour pause. */
  resumeTour: () => void;
  /** Show a highlight callout. Returns a promise that resolves on dismiss. */
  showHighlight: (data: ReplayHighlightData) => Promise<void>;
  /** Dismiss the current highlight and resume replay. */
  dismissHighlight: () => void;

  /** Whether to show the "Play Demo Flow" button hint after welcome dismiss. */
  showDemoHint: boolean;
  /** Skip tour overlays and highlight callouts (fast replay mode). */
  skipAnnotations: boolean;
  /** Skip every guided-tour pause too (Skip-to-End fast-forward). */
  skipTourPauses: boolean;
  /** Dismiss the demo button hint. */
  dismissDemoHint: () => void;
}

export const useReplayStore = create<ReplayStore>((set, get) => ({
  mode: "off",
  replayVariant: "detailed",
  speedMultiplier: 1,
  isPaused: false,
  tourStepIndex: -1,
  _abortController: null,
  _resumeResolver: null,
  activeHighlight: null,
  _highlightResolver: null,
  showDemoHint: false,
  skipAnnotations: false,
  skipTourPauses: false,

  startReplay: (variant = "detailed") => {
    // Cancel any existing replay
    const prev = get()._abortController;
    if (prev) prev.abort();
    const controller = new AbortController();
    set({
      mode: "playing",
      replayVariant: variant,
      speedMultiplier: variant === "skip" ? 500 : variant === "fast" ? 4 : 1,
      skipAnnotations: variant === "fast" || variant === "skip",
      skipTourPauses: variant === "skip",
      _abortController: controller,
      isPaused: false,
      tourStepIndex: -1,
      _resumeResolver: null,
    });
  },

  stopReplay: () => {
    const hlResolve = get()._highlightResolver;
    if (hlResolve) hlResolve();
    set({
      mode: "done",
      replayVariant: "detailed",
      _abortController: null,
      isPaused: false,
      tourStepIndex: -1,
      _resumeResolver: null,
      activeHighlight: null,
      _highlightResolver: null,
      speedMultiplier: 1,
      skipAnnotations: false,
      skipTourPauses: false,
    });
  },

  cancelReplay: () => {
    const { _abortController: ctrl, _resumeResolver: resolve, _highlightResolver: hlResolve } = get();
    if (resolve) resolve();
    if (hlResolve) hlResolve();
    if (ctrl) ctrl.abort();
    set({
      mode: "off",
      replayVariant: "detailed",
      _abortController: null,
      isPaused: false,
      tourStepIndex: -1,
      _resumeResolver: null,
      activeHighlight: null,
      _highlightResolver: null,
      speedMultiplier: 1,
      skipAnnotations: false,
      skipTourPauses: false,
    });
  },

  setSpeed: (multiplier: number) => {
    set({ speedMultiplier: Math.max(0.25, Math.min(multiplier, 10)) });
  },

  pauseForTour: (stepIndex: number) =>
    new Promise<void>((resolve) => {
      /* Skip-to-End fast-forwards through every tour stop automatically. */
      if (get().skipTourPauses) {
        resolve();
        return;
      }
      set({
        isPaused: true,
        tourStepIndex: stepIndex,
        _resumeResolver: resolve,
      });
    }),

  resumeTour: () => {
    const resolve = get()._resumeResolver;
    if (resolve) resolve();
    set({
      isPaused: false,
      tourStepIndex: -1,
      _resumeResolver: null,
    });
  },

  showHighlight: (data: ReplayHighlightData) =>
    new Promise<void>((resolve) => {
      /* In fast/skip mode, resolve immediately without showing the callout. */
      if (get().skipAnnotations) {
        resolve();
        return;
      }
      set({
        activeHighlight: data,
        _highlightResolver: resolve,
      });
    }),

  dismissHighlight: () => {
    const resolve = get()._highlightResolver;
    if (resolve) resolve();
    set({
      activeHighlight: null,
      _highlightResolver: null,
    });
  },

  dismissDemoHint: () => set({ showDemoHint: false }),
}));
