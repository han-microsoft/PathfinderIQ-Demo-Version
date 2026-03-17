/**
 * @module ResizableGraph
 *
 * Resizable container for the graph topology panel — wraps its children
 * in a vertically resizable region with a drag handle at the bottom edge.
 *
 * Uses a **ratio** (0 – 1) instead of fixed pixels so the graph / chat
 * split scales proportionally when the browser window is resized. The
 * ratio is persisted to `localStorage` under `'graph-ratio'`.
 *
 * Default split: 50 / 50. Clamped between 10 % and 90 % so neither
 * panel can be fully hidden.
 *
 * @dependents
 *   Rendered by the root App layout in the left column above the chat panel.
 */
import { useState, useRef, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'graph-ratio';
const DEFAULT_RATIO = 0.5;
const MIN_RATIO = 0.1;
const MAX_RATIO = 0.9;

export function ResizableGraph({ children }: { children: React.ReactNode }) {
  /* ---- ratio state (persisted) ---- */
  const [ratio, setRatio] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const n = Number(saved);
        if (!isNaN(n) && n >= MIN_RATIO && n <= MAX_RATIO) return n;
      }
    } catch { /* ignore */ }
    return DEFAULT_RATIO;
  });

  /* ---- drag refs ---- */
  const dragging = useRef(false);
  const startY = useRef(0);
  const startRatio = useRef(ratio);
  const ratioRef = useRef(ratio);
  const wrapperRef = useRef<HTMLDivElement>(null);
  useEffect(() => { ratioRef.current = ratio; }, [ratio]);

  /* pointermove — compute new ratio from drag delta */
  const onDocMove = useCallback((e: PointerEvent) => {
    if (!dragging.current) return;
    /* Parent is the flex-col <main> that the graph + chat share */
    const parentH = wrapperRef.current?.parentElement?.clientHeight ?? 1;
    const deltaRatio = (e.clientY - startY.current) / parentH;
    setRatio(Math.max(MIN_RATIO, Math.min(MAX_RATIO, startRatio.current + deltaRatio)));
  }, []);

  /* pointerup — persist, detach */
  const onDocUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    try { localStorage.setItem(STORAGE_KEY, String(ratioRef.current)); } catch { /* ignore */ }
    document.removeEventListener('pointermove', onDocMove);
    document.removeEventListener('pointerup', onDocUp);
  }, [onDocMove]);

  /* pointerdown on handle — start drag */
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    dragging.current = true;
    startY.current = e.clientY;
    startRatio.current = ratioRef.current;
    document.addEventListener('pointermove', onDocMove);
    document.addEventListener('pointerup', onDocUp);
  }, [onDocMove, onDocUp]);

  /* Safety cleanup on unmount */
  useEffect(() => {
    return () => {
      document.removeEventListener('pointermove', onDocMove);
      document.removeEventListener('pointerup', onDocUp);
    };
  }, [onDocMove, onDocUp]);

  return (
    <div
      ref={wrapperRef}
      className="relative flex flex-col min-h-0"
      style={{ flex: `0 0 ${ratio * 100}%` }}
    >
      <div className="flex-1 overflow-hidden min-h-0">
        {children}
      </div>
      {/* Drag handle */}
      <div
        className="h-2.5 cursor-row-resize shrink-0
                   bg-neutral-bg3 hover:bg-neutral-bg4 active:bg-brand/20
                   transition-colors z-10 flex items-center justify-center group/handle"
        onPointerDown={onPointerDown}
      >
        <div className="w-10 h-1 rounded-full bg-neutral-bg5
                        group-hover/handle:bg-brand/70 transition-colors" />
      </div>
    </div>
  );
}
