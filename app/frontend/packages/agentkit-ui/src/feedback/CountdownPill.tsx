/**
 * CountdownPill — domain-blind floating countdown overlay.
 *
 * Generic "waiting N seconds" pill (e.g. LLM rate-limit retry). The consumer
 * resolves the countdown source (a store, a fetch header, …) and passes the
 * seconds remaining; this component owns the local 1 Hz tick + fade.
 *
 * Animation contract (consumer-supplied global CSS, see theme/TOKENS.md):
 *   - `animate-fade-in`, `animate-spin-slow`
 */
import { useEffect, useState, type ReactNode } from "react";

export interface CountdownPillProps {
  /** Seconds remaining. `null`/<=0 hides the pill. Changing it restarts the tick. */
  seconds: number | null;
  /** Leading text before the countdown number. */
  label?: string;
  /** Icon/emoji shown spinning at the left. */
  icon?: ReactNode;
  /** Suffix after the number (default "s"). */
  unit?: string;
}

/**
 * Floating top-left pill — appears while `seconds` is positive, ticks down
 * locally every second, hides at zero.
 */
export function CountdownPill({
  seconds,
  label = "Waiting — retrying in ",
  icon = "⏳",
  unit = "s",
}: CountdownPillProps) {
  const [remaining, setRemaining] = useState<number | null>(null);

  useEffect(() => {
    if (seconds === null || seconds <= 0) {
      setRemaining(null);
      return;
    }
    setRemaining(seconds);
    const id = setInterval(() => {
      setRemaining((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(id);
          return null;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [seconds]);

  if (remaining === null) return null;

  return (
    <div className="fixed top-16 left-6 z-50 flex items-center gap-3 px-5 py-3 rounded-xl bg-neutral-bg2/80 backdrop-blur-sm border border-border shadow-lg animate-fade-in">
      <span className="text-xl animate-spin-slow">{icon}</span>
      <div className="text-sm">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-bold text-text-primary text-base">
          {remaining}
          {unit}
        </span>
      </div>
    </div>
  );
}
