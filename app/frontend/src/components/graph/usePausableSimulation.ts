/**
 * @module usePausableSimulation
 *
 * Pause/resume hook for the force-graph physics simulation.
 *
 * Provides two pause modes:
 *   1. **Auto-pause on hover** — `handleMouseEnter` freezes the simulation
 *      so nodes stop jittering while the user inspects tooltips.
 *      `handleMouseLeave` resumes after a 300 ms debounce delay.
 *   2. **Manual pause** — `handleTogglePause` locks the simulation in a
 *      frozen state until explicitly toggled off, overriding hover-resume.
 *
 * Operates on any ref implementing `{ setFrozen(boolean): void }`,
 * which is satisfied by {@link GraphCanvasHandle}.
 *
 * @param canvasRef — React ref to the graph canvas imperative handle
 * @returns `{ isPaused, handleMouseEnter, handleMouseLeave, handleTogglePause, resetPause }`
 *
 * @dependents
 *   Used by {@link GraphTopologyViewer} to wire pause controls to the
 *   header bar and canvas mouse events.
 */
import { useState, useCallback, useRef, useEffect, type RefObject } from 'react';

interface PausableSimulationResult {
  isPaused: boolean;
  handleMouseEnter: () => void;
  handleMouseLeave: () => void;
  handleTogglePause: () => void;
  resetPause: () => void;
}

interface Freezable {
  setFrozen: (frozen: boolean) => void;
}

export function usePausableSimulation(
  canvasRef: RefObject<Freezable | null>,
): PausableSimulationResult {
  const [isPaused, setIsPaused] = useState(false);
  const [manualPause, setManualPause] = useState(false);
  const resumeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Grace period: suppress hover-freeze for the first 5 s so the layout can
  // expand, even if the user's cursor is already over the graph on mount.
  const graceRef = useRef(true);

  const handleMouseEnter = useCallback(() => {
    if (graceRef.current) return;           // inside grace period — ignore
    if (resumeTimeoutRef.current) {
      clearTimeout(resumeTimeoutRef.current);
      resumeTimeoutRef.current = null;
    }
    canvasRef.current?.setFrozen(true);
    setIsPaused(true);
  }, [canvasRef]);

  const handleMouseLeave = useCallback(() => {
    if (graceRef.current) return;           // inside grace period — ignore
    if (manualPause) return;
    resumeTimeoutRef.current = setTimeout(() => {
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
      resumeTimeoutRef.current = null;
    }, 300);
  }, [manualPause, canvasRef]);

  const handleTogglePause = useCallback(() => {
    graceRef.current = false;               // manual toggle ends grace period
    if (manualPause) {
      setManualPause(false);
      canvasRef.current?.setFrozen(false);
      setIsPaused(false);
    } else {
      setManualPause(true);
      canvasRef.current?.setFrozen(true);
      setIsPaused(true);
    }
  }, [manualPause, canvasRef]);

  const resetPause = useCallback(() => {
    setManualPause(false);
    canvasRef.current?.setFrozen(false);
    setIsPaused(false);
  }, [canvasRef]);

  /* Auto-pause after 5 s so the layout settles then stops jiggling. */
  useEffect(() => {
    const timer = setTimeout(() => {
      graceRef.current = false;
      if (!manualPause) {
        setManualPause(true);
        canvasRef.current?.setFrozen(true);
        setIsPaused(true);
      }
    }, 5000);
    return () => clearTimeout(timer);
    // Run once on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current);
    };
  }, []);

  return { isPaused, handleMouseEnter, handleMouseLeave, handleTogglePause, resetPause };
}
