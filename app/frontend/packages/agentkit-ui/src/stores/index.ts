/**
 * agentkit-ui / stores — reusable zustand stores.
 *
 * toastStore   : transient notification queue (pairs with @agentkit-ui/feedback Toaster).
 * paletteStore : open/close state for a command palette + help overlay.
 *
 * `zustand` is a peer dependency.
 */
export { useToastStore } from "./toastStore";
export type { ToastTone, ToastEntry, ToastInput } from "./toastStore";
export { usePaletteStore } from "./paletteStore";
