/**
 * agentkit-ui / hooks — domain-blind React hooks.
 *
 * useAutoScroll  : smart scroll-to-bottom (chat timelines, log views).
 * usePersistence : localStorage sync helper.
 * useTypewriter  : character-by-character streaming text animation.
 *
 * Zero domain coupling — peer-dep `react` only.
 */
export { useAutoScroll } from "./useAutoScroll";
export { usePersistence } from "./usePersistence";
export { useTypewriter } from "./useTypewriter";
export { useKeydownDispatcher, isEditableTarget } from "./useKeydownDispatcher";
export type { KeyBinding } from "./useKeydownDispatcher";
export { useOutsideClick } from "./useOutsideClick";
export { useDebouncedValue } from "./useDebouncedValue";
export type { UseDebouncedValueOptions } from "./useDebouncedValue";
