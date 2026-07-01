/**
 * agentkit-ui / hooks / useKeydownDispatcher — document-level keyboard
 * shortcut engine.
 *
 * Domain-blind. The consumer passes a binding table; the hook installs one
 * `keydown` listener, skips events that originate in an editable surface
 * (unless a binding opts in via `allowInEditable`), matches modifier state
 * exactly, and fires the first matching binding's handler. Each handler
 * decides whether to `preventDefault` (it receives the event).
 *
 * Replaces hand-rolled `document.addEventListener("keydown", …)` blocks.
 * The consumer keeps its app-specific bindings (which keys do what); the
 * hook owns the lifecycle + editable guard + modifier matching.
 */
import { useEffect } from "react";

export interface KeyBinding {
  /** `KeyboardEvent.key` to match. Case-insensitive for single letters. */
  key: string;
  /** Require Ctrl OR Meta (⌘) to be held. Default: must be absent. */
  ctrlOrMeta?: boolean;
  /** Require Alt. Default: must be absent. */
  alt?: boolean;
  /** Require Shift. Default: Shift state is ignored unless set. */
  shift?: boolean;
  /** Fire even when the event target is an editable surface (input/textarea/…). */
  allowInEditable?: boolean;
  /** Handler — receives the event so it can `preventDefault` selectively. */
  handler: (e: KeyboardEvent) => void;
}

/** True when the event originated inside an editable surface. */
export function isEditableTarget(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  if (!t) return false;
  const tag = t.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return Boolean(t.isContentEditable);
}

function matches(b: KeyBinding, e: KeyboardEvent): boolean {
  if (b.key.length === 1) {
    if (e.key.toLowerCase() !== b.key.toLowerCase()) return false;
  } else if (e.key !== b.key) {
    return false;
  }
  const wantsMod = Boolean(b.ctrlOrMeta);
  const hasMod = e.ctrlKey || e.metaKey;
  if (wantsMod !== hasMod) return false;
  if (Boolean(b.alt) !== e.altKey) return false;
  if (b.shift !== undefined && b.shift !== e.shiftKey) return false;
  return true;
}

/**
 * Install a keyboard-shortcut dispatcher for the lifetime of the component.
 *
 * @param bindings ordered table; the first match wins.
 * @param target the listener root (default `document`).
 *
 * Bindings are read on every keystroke from the latest array, so a consumer
 * that rebuilds the array each render gets fresh handlers without re-binding.
 */
export function useKeydownDispatcher(
  bindings: KeyBinding[],
  target: Document = document,
): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      for (const b of bindings) {
        if (!matches(b, e)) continue;
        if (!b.allowInEditable && isEditableTarget(e)) continue;
        b.handler(e);
        return;
      }
    };
    target.addEventListener("keydown", onKeyDown);
    return () => target.removeEventListener("keydown", onKeyDown);
  }, [bindings, target]);
}
