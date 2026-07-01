/**
 * agentkit-ui / feedback — domain-blind overlays & notifications.
 *
 * Props-driven, zero store coupling. The consumer owns state (toast store,
 * palette open-flag, countdown source) and injects it.
 *   - Toaster       : fixed toast stack (tone → generic status tokens, overridable).
 *   - HelpOverlay   : injected-shortcut cheat-sheet modal (portal to body).
 *   - CountdownPill : generic "retrying in N s" floating pill (self-ticking).
 */
export { Toaster } from "./Toaster";
export type { ToastTone, ToastEntry, ToasterProps } from "./Toaster";
export { HelpOverlay } from "./HelpOverlay";
export type { Shortcut, ShortcutGroup, HelpOverlayProps } from "./HelpOverlay";
export { CountdownPill } from "./CountdownPill";
export type { CountdownPillProps } from "./CountdownPill";
export { CommandPaletteBase } from "./CommandPaletteBase";
export type { Command, CommandPaletteBaseProps } from "./CommandPaletteBase";
export {
  TimedProgressBar,
  TimedProgressPanel,
  progressFraction,
  formatSeconds,
} from "./TimedProgress";
export type { TimedProgressProps, TimedProgressPanelProps } from "./TimedProgress";
