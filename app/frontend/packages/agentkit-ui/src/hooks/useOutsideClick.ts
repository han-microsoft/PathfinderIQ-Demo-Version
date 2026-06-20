/**
 * agentkit-ui / hooks / useOutsideClick — fire a callback on a pointer-down
 * outside the referenced element.
 *
 * The dropdown/popover/menu "click away to close" pattern, deduplicated.
 * Only listens while `active` is true (so a closed menu adds no listener).
 */
import { useEffect, type RefObject } from "react";

/**
 * @param ref     element whose interior clicks are ignored.
 * @param onOutside called on a `mousedown` whose target is outside `ref`.
 * @param active  attach the listener only while true (e.g. menu open).
 */
export function useOutsideClick(
  ref: RefObject<HTMLElement | null>,
  onOutside: () => void,
  active = true,
): void {
  useEffect(() => {
    if (!active) return;
    function onMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onOutside();
      }
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [ref, onOutside, active]);
}
