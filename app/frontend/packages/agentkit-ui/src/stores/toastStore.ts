/**
 * agentkit-ui / stores / toastStore — transient notification queue (zustand).
 *
 * Domain-blind. Any component or non-React watcher pushes a toast via
 * `pushToast()`; the `@agentkit-ui/feedback` Toaster renders the queue.
 * Each toast auto-dismisses after `durationMs` (0 = sticky).
 */
import { create } from "zustand";

/** Toast severity tone — drives the left strip + icon colour in the renderer. */
export type ToastTone = "info" | "success" | "warning" | "error";

/** One toast record. `id` is an auto-incrementing number kept in the store. */
export interface ToastEntry {
  id: number;
  title: string;
  body?: string;
  tone: ToastTone;
  /** Milliseconds until auto-dismiss. 0 disables. */
  durationMs: number;
  /** When true, the toast flashes/pulses to grab attention. */
  pulse?: boolean;
}

/** Argument to `pushToast` — `id` is assigned by the store. */
export type ToastInput = Omit<ToastEntry, "id">;

interface ToastStore {
  toasts: ToastEntry[];
  /** Append a toast. Returns the assigned id so callers can dismiss it early. */
  pushToast: (input: ToastInput) => number;
  /** Remove the toast with the given id. No-op if id is gone. */
  dismissToast: (id: number) => void;
  /** Clear all toasts. */
  clearToasts: () => void;
}

/* Monotonic id counter — module scope so test store resets don't collide. */
let nextId = 1;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],

  pushToast: (input) => {
    const id = nextId++;
    const entry: ToastEntry = { id, ...input };
    set((state) => ({ toasts: [...state.toasts, entry] }));
    return id;
  },

  dismissToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  clearToasts: () => set({ toasts: [] }),
}));
