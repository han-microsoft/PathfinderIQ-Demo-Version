/**
 * agentkit-ui / hooks / useDebouncedValue — debounce a rapidly-changing
 * value, with an `immediate` escape hatch.
 *
 * Built for streaming text: re-rendering heavy markdown on every token
 * (~30–50/s) is wasteful, so debounce while streaming and flush instantly
 * when streaming ends. `immediate=true` bypasses the debounce and applies
 * the latest value synchronously (final state / reload / non-streaming).
 */
import { useEffect, useRef, useState } from "react";

export interface UseDebouncedValueOptions {
  /** Debounce interval in ms. Default 150. */
  delayMs?: number;
  /** When true, apply the value immediately (no debounce). Default false. */
  immediate?: boolean;
}

/**
 * @returns the debounced value. Tracks `value` at most once per `delayMs`
 *   while `immediate` is false; applies instantly when `immediate` is true.
 */
export function useDebouncedValue<T>(value: T, options: UseDebouncedValueOptions = {}): T {
  const { delayMs = 150, immediate = false } = options;
  const [debounced, setDebounced] = useState<T>(value);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (immediate) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setDebounced(value);
      return;
    }
    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        setDebounced(value);
        timerRef.current = null;
      }, delayMs);
    }
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [value, immediate, delayMs]);

  return debounced;
}
