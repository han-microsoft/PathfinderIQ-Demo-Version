/**
 * @module useTypewriter
 *
 * useTypewriter — progressively reveals a string over a fixed duration.
 *
 * Used by ToolCallDisplay as the FALLBACK animation when the backend
 * delivers tool arguments in a single chunk (the Azure AI Foundry
 * Agents API aggregates ``function_call.arguments`` server-side rather
 * than streaming them token-by-token). When TOOL_CALL_DELTA events do
 * arrive — e.g. when a future backend streams real per-chunk fragments
 * — the raw streaming view in ToolCallDisplay takes precedence and
 * this hook is bypassed.
 *
 * The hook resets when ``value`` changes identity, so callers can pass
 * the final argument string and let the hook animate the reveal over
 * ``durationMs`` milliseconds. Returns the currently-visible substring.
 */

import { useEffect, useRef, useState } from "react";

/**
 * Animate ``value`` character-by-character over ``durationMs``.
 *
 * @param value      The full target string to reveal.
 * @param durationMs Total animation duration in milliseconds.
 * @returns          The currently-visible prefix of ``value``.
 */
export function useTypewriter(value: string, durationMs: number): string {
  // Track the most-recent visible prefix so re-renders within one
  // animation cycle do not restart the reveal.
  const [visible, setVisible] = useState<string>("");
  // Raf handle so we can cancel cleanly on unmount or value change.
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    // Reset visible state on each new target value; the new animation
    // begins from an empty prefix.
    setVisible("");
    if (!value) return;
    const start = performance.now();
    const total = Math.max(1, durationMs);
    const tick = (now: number) => {
      // Compute the prefix length proportional to elapsed time.
      const elapsed = now - start;
      const ratio = Math.min(1, elapsed / total);
      const cutoff = Math.max(1, Math.floor(value.length * ratio));
      setVisible(value.slice(0, cutoff));
      if (ratio < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [value, durationMs]);

  return visible;
}
