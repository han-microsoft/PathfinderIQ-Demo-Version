/**
 * Toaster — domain-blind, props-driven toast stack.
 *
 * Pure presentational. The consumer owns toast state (a store, context,
 * whatever) and passes the active toasts + a dismiss callback. Visual
 * tone → colour defaults to the generic `status-*` token group; a
 * consumer with a richer palette overrides `toneStrip` / `toneIconColor`.
 *
 * Animation contract (consumer-supplied global CSS, see theme/TOKENS.md):
 *   - `fade-in` keyframe + `--motion-ease` token (enter animation)
 *   - `pulseClassName` (optional) — a consumer animation class for "fresh" toasts
 */
import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ToastTone = "info" | "success" | "warning" | "error";

export interface ToastEntry {
  id: string | number;
  tone: ToastTone;
  title: string;
  body?: string;
  /** Auto-dismiss after this many ms. `0` (or less) = sticky. */
  durationMs: number;
  /** When true, applies `pulseClassName` for a one-shot highlight. */
  pulse?: boolean;
}

export interface ToasterProps {
  toasts: ToastEntry[];
  onDismiss: (id: string | number) => void;
  /** Per-tone left-strip border class. Defaults to generic status tokens. */
  toneStrip?: Record<ToastTone, string>;
  /** Per-tone icon colour class. Defaults to generic status tokens. */
  toneIconColor?: Record<ToastTone, string>;
  /** Animation class applied when `toast.pulse` is true. */
  pulseClassName?: string;
}

const TONE_ICON: Record<ToastTone, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

/* Domain-blind defaults — generic status token group. Consumers with a
   bespoke severity palette override via props. */
const DEFAULT_TONE_STRIP: Record<ToastTone, string> = {
  info: "border-l-status-info",
  success: "border-l-status-success",
  warning: "border-l-status-warning",
  error: "border-l-status-error",
};

const DEFAULT_TONE_ICON_COLOR: Record<ToastTone, string> = {
  info: "text-status-info",
  success: "text-status-success",
  warning: "text-status-warning",
  error: "text-status-error",
};

function ToastCard({
  toast,
  onDismiss,
  toneStrip,
  toneIconColor,
  pulseClassName,
}: {
  toast: ToastEntry;
  onDismiss: (id: string | number) => void;
  toneStrip: Record<ToastTone, string>;
  toneIconColor: Record<ToastTone, string>;
  pulseClassName: string;
}) {
  const Icon = TONE_ICON[toast.tone];

  /* Auto-dismiss timer. durationMs <= 0 disables (sticky toast). */
  useEffect(() => {
    if (toast.durationMs <= 0) return;
    const timer = window.setTimeout(() => onDismiss(toast.id), toast.durationMs);
    return () => window.clearTimeout(timer);
  }, [toast.id, toast.durationMs, onDismiss]);

  return (
    <div
      data-testid={`toast-${toast.tone}`}
      role="status"
      className={[
        "pointer-events-auto flex items-start gap-2 rounded-lg border border-border bg-neutral-bg1 px-3 py-2 shadow-lg",
        "border-l-[3px]",
        toneStrip[toast.tone],
        "animate-[fade-in_150ms_var(--motion-ease)]",
        toast.pulse ? pulseClassName : "",
      ].join(" ")}
      style={{ minWidth: 260, maxWidth: 360 }}
    >
      <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${toneIconColor[toast.tone]}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary leading-tight">{toast.title}</p>
        {toast.body && (
          <p className="text-xs text-text-secondary mt-0.5 leading-snug break-words">{toast.body}</p>
        )}
      </div>
      <button
        data-testid={`toast-dismiss-${toast.id}`}
        onClick={() => onDismiss(toast.id)}
        className="shrink-0 p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
        aria-label="Dismiss notification"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

/**
 * Fixed bottom-right toast stack. `pointer-events-none` on the wrapper so
 * the column never blocks the UI beneath it; each card re-enables its own.
 */
export function Toaster({
  toasts,
  onDismiss,
  toneStrip = DEFAULT_TONE_STRIP,
  toneIconColor = DEFAULT_TONE_ICON_COLOR,
  pulseClassName = "",
}: ToasterProps) {
  return (
    <div
      data-testid="toaster"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end"
    >
      {toasts.map((t) => (
        <ToastCard
          key={t.id}
          toast={t}
          onDismiss={onDismiss}
          toneStrip={toneStrip}
          toneIconColor={toneIconColor}
          pulseClassName={pulseClassName}
        />
      ))}
    </div>
  );
}
