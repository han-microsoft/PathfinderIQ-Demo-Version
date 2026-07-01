/**
 * agentkit-ui / feedback / TimedProgress — time-based progress for a
 * single-shot (non-streaming) operation.
 *
 * When a backend op gives no progress events, interpolate against a rolling
 * estimate with a logarithmic curve that approaches but never reaches 100%
 * (so the bar visibly stalls near the end instead of claiming completion;
 * the parent signals done by unmounting). Domain-blind: the consumer passes
 * `startedAt` + `estimateMs` (+ optional rotating status messages); the
 * components own the tick + easing.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

/**
 * Asymptotic progress curve in [0, 0.99). `1 - exp(-1.6 t)` hits 0.80 at
 * t=1, 0.95 at t=2, 0.99 at t≈2.9 (t = elapsed/estimate).
 */
export function progressFraction(elapsedMs: number, estimateMs: number): number {
  if (estimateMs <= 0) return 0;
  const t = elapsedMs / estimateMs;
  return Math.min(0.99, 1 - Math.exp(-1.6 * t));
}

/** Format ms as "Xs" or "Xm Ys". */
export function formatSeconds(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** 100 ms render tick while `active`. Returns current `Date.now()`. */
function useTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

export interface TimedProgressProps {
  /** `Date.now()` when the op started, or null when idle (renders nothing). */
  startedAt: number | null;
  /** Rolling estimate in ms. Falsy → renders nothing. */
  estimateMs: number | null;
}

/** Slim 2px header progress bar. Renders nothing when idle. */
export function TimedProgressBar({ startedAt, estimateMs }: TimedProgressProps) {
  const active = startedAt !== null;
  const now = useTick(active);
  if (!active || !startedAt || !estimateMs) return null;
  const pct = progressFraction(now - startedAt, estimateMs) * 100;
  return (
    <div
      data-testid="timed-progress-bar"
      className="h-0.5 w-full bg-neutral-bg3 overflow-hidden"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
    >
      <div className="h-full bg-brand transition-[width] duration-100 ease-out" style={{ width: `${pct}%` }} />
    </div>
  );
}

export interface TimedProgressPanelProps extends TimedProgressProps {
  /** Rotating status messages cycled while the op runs. */
  messages: readonly string[];
  /** Linger per message before cycling. Default 2500 ms. */
  messageRotateMs?: number;
  /** Icon centred in the spinner stack. */
  icon?: ReactNode;
  /** Footnote under the bar (e.g. "Estimating from your last run"). */
  footnote?: ReactNode;
}

/** Body-sized crunching status: spinner + rotating message + elapsed/ETA. */
export function TimedProgressPanel({
  startedAt,
  estimateMs,
  messages,
  messageRotateMs = 2500,
  icon,
  footnote,
}: TimedProgressPanelProps) {
  const active = startedAt !== null;
  const now = useTick(active);

  const [statusIdx, setStatusIdx] = useState(0);
  useEffect(() => {
    if (!active || messages.length === 0) {
      setStatusIdx(0);
      return;
    }
    const id = window.setInterval(
      () => setStatusIdx((i) => (i + 1) % messages.length),
      messageRotateMs,
    );
    return () => window.clearInterval(id);
  }, [active, messages.length, messageRotateMs]);

  if (!active || !startedAt || !estimateMs) return null;

  const elapsed = now - startedAt;
  const pct = progressFraction(elapsed, estimateMs) * 100;
  const remainingMs = Math.max(1000, estimateMs - elapsed);

  return (
    <div
      data-testid="timed-progress-panel"
      className="flex flex-col items-center justify-center gap-3 py-8 px-6 text-center"
    >
      <div className="relative">
        <Loader2 className="h-10 w-10 text-brand/30 animate-spin" />
        {icon && <div className="absolute inset-0 m-auto flex items-center justify-center">{icon}</div>}
      </div>

      <div className="text-sm font-semibold text-text-primary">{messages[statusIdx]}</div>

      <div className="w-full max-w-xs">
        <div
          className="h-1.5 w-full bg-neutral-bg3 rounded-full overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
        >
          <div className="h-full bg-brand transition-[width] duration-100 ease-out" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex items-center justify-between mt-1.5 text-label font-mono text-text-muted">
          <span data-testid="timed-progress-elapsed">{formatSeconds(elapsed)} elapsed</span>
          <span data-testid="timed-progress-eta">~{formatSeconds(remainingMs)} left</span>
        </div>
      </div>

      {footnote && <p className="text-label text-text-muted max-w-xs">{footnote}</p>}
    </div>
  );
}
