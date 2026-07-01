/**
 * agentkit-ui — reusable, domain-blind React component kit.
 *
 * Top-level barrel. Prefer the sub-path imports (`@agentkit-ui/primitives`,
 * `@agentkit-ui/chat`, `@agentkit-ui/hooks`) at call sites for clarity; this
 * root re-export exists for convenience + the standalone examples app.
 */
export * from "./primitives";
export * from "./chat";
export * from "./hooks";
export * from "./feedback";
export * from "./sse";
export * from "./foundation";
export * from "./http";
export * from "./layout";
// Stores: re-exported explicitly — `feedback` already owns the `ToastTone`
// / `ToastEntry` render-prop types at the root barrel, so stores contributes
// only the hooks + the store-side `ToastInput`. (The `@agentkit-ui/stores`
// sub-path still exports its own toast types for standalone use.)
export { useToastStore, usePaletteStore } from "./stores";
export type { ToastInput } from "./stores";
