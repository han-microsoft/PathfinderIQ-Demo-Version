/**
 * @module useResizable
 *
 * Drag-to-resize hook — provides size state and pointer event handlers
 * for creating resizable UI regions.
 *
 * Tracks a single-axis size value (x or y) that updates as the user
 * drags. The size is persisted to `localStorage` under the provided
 * `storageKey` so the user's preference survives page reloads.
 *
 * Uses document-level pointermove/pointerup listeners (attached on
 * pointerdown, removed on pointerup) so the drag never "sticks" when
 * the cursor moves faster than the handle element can follow.
 * A size ref avoids stale-closure bugs in the pointerup handler.
 *
 * @param axis — `'x'` for horizontal resizing, `'y'` for vertical
 * @param opts.initial — default size in pixels
 * @param opts.min     — minimum allowed size
 * @param opts.max     — maximum allowed size
 * @param opts.storageKey — localStorage key for persistence
 * @param opts.invert  — invert drag direction (for right-to-left panels)
 *
 * @returns `{ size, handleProps }` where `handleProps` is spread onto
 *   the drag handle element (only `onPointerDown` — move/up are global)
 *
 * @dependents
 *   Used by {@link ResizableGraph} for the graph panel height.
 *   Used by App.tsx for the left nav sidebar and right session sidebar.
 */
import { useState, useRef, useCallback, useEffect } from 'react';

interface UseResizableOptions {
  initial: number;
  min: number;
  max: number;
  storageKey: string;
  invert?: boolean;
}

export function useResizable(axis: 'x' | 'y', opts: UseResizableOptions) {
  const { min, max, storageKey, invert = false } = opts;

  const [size, setSize] = useState(() => {
    const saved = localStorage.getItem(storageKey);
    return saved ? Math.max(min, Math.min(max, Number(saved))) : opts.initial;
  });

  /* Refs track mutable drag state — avoids stale closures in global listeners */
  const dragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(0);
  /** Mirror of `size` state — read inside global pointerup to persist the
   *  current value without depending on a stale closure. */
  const sizeRef = useRef(size);
  useEffect(() => { sizeRef.current = size; }, [size]);

  /**
   * Global pointermove — updates size while dragging.
   * Attached to `document` on pointerdown, removed on pointerup.
   * Uses the native PointerEvent (not React.PointerEvent) because
   * it runs outside the React event system.
   */
  const onDocumentPointerMove = useCallback((e: PointerEvent) => {
    if (!dragging.current) return;
    const pos = axis === 'x' ? e.clientX : e.clientY;
    const delta = invert
      ? startPos.current - pos
      : pos - startPos.current;
    setSize(Math.max(min, Math.min(max, startSize.current + delta)));
  }, [axis, invert, min, max]);

  /**
   * Global pointerup — ends the drag, persists size, removes global listeners.
   * Reads sizeRef (not `size`) to avoid the stale-closure problem where the
   * callback captured an outdated `size` value.
   */
  const onDocumentPointerUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    localStorage.setItem(storageKey, String(sizeRef.current));
    document.removeEventListener('pointermove', onDocumentPointerMove);
    document.removeEventListener('pointerup', onDocumentPointerUp);
  }, [storageKey, onDocumentPointerMove]);

  /**
   * Handle-level pointerdown — starts the drag and attaches global listeners.
   * setPointerCapture is intentionally NOT used here; document-level listeners
   * are more reliable across browsers when the pointer leaves the handle.
   */
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragging.current = true;
    startPos.current = axis === 'x' ? e.clientX : e.clientY;
    startSize.current = sizeRef.current;
    document.addEventListener('pointermove', onDocumentPointerMove);
    document.addEventListener('pointerup', onDocumentPointerUp);
  }, [axis, onDocumentPointerMove, onDocumentPointerUp]);

  /* Safety cleanup — remove global listeners if the component unmounts mid-drag */
  useEffect(() => {
    return () => {
      document.removeEventListener('pointermove', onDocumentPointerMove);
      document.removeEventListener('pointerup', onDocumentPointerUp);
    };
  }, [onDocumentPointerMove, onDocumentPointerUp]);

  return {
    size,
    handleProps: { onPointerDown },
  };
}
