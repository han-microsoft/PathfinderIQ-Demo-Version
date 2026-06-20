/**
 * ToolResultCard — shared scaffold for every tool result renderer.
 *
 * Module role:
 *   Codifies the 4-band layout proven by GraphEnvelopeResult (the audit
 *   benchmark, see specs/couturier_20260516_tool_renderers.md R1):
 *     1. `scope`   — identifier badges naming WHAT the tool ran against
 *     2. `signal`  — summary chips naming the salient signal of the answer
 *     3. body      — caller-supplied detail block (table, cards, prose)
 *     4. `note`    — optional contextual banner (warning or info)
 *   And a fifth single-purpose mode: `error` collapses the entire card
 *   to a red banner with a typed detail string.
 *
 *   Every renderer consumes this so visual coherence (corner radius,
 *   border tone, padding, typography size scale) is enforced once.
 *   Arbitrary `text-[0.NNem]` utilities are forbidden in renderers that
 *   live inside the scaffold; use Tailwind's `text-micro`/`text-label`/
 *   `text-xs`/`text-sm` tokens which resolve via tokens.css.
 *
 * Constraints:
 *   - All structural tokens (radius, border, max-h, padding) are
 *     locked here. Renderers MUST NOT override them via className.
 *   - The `data-tool-card` attribute is exposed so the chat-stream
 *     e2e suite can assert that every renderer landed inside the
 *     scaffold (registry-coverage regression).
 */

import type { ReactNode } from "react";

export type SignalTone = "neutral" | "accent" | "success" | "warning" | "error";
export type NoteTone = "info" | "warning" | "error";

export interface ScopeBadge {
  label: string;
  value: string;
}

export interface SignalChip {
  label: string;
  value: string | number;
  tone?: SignalTone;
}

export interface ToolResultCardProps {
  /** Identifier badges — e.g. station/bus/voltage_kv, or {agent_id, status}. */
  scope?: ScopeBadge[];
  /** Headline counts/chips. Rendered as inline chips in the signal band. */
  signal?: SignalChip[];
  /** Optional contextual banner below the signal band. */
  note?: string | null;
  /** Tone of the note banner. */
  noteTone?: NoteTone;
  /**
   * Error envelope short-circuit. When set the card renders ONLY the
   * red error banner (no scope, no signal, no body). Use the canonical
   * ToolResultError component (in JsonFallback.tsx) for non-card error
   * spots; this prop is the in-card variant.
   */
  error?: { detail: string } | null;
  /** Body content — table, cards, prose. Rendered after note. */
  children?: ReactNode;
}

/* Signal chip tone → Tailwind classes. Tokens only (resolved via
   tokens.css through tailwind.config.js). */
const SIGNAL_TONE_CLASS: Record<SignalTone, string> = {
  neutral: "bg-neutral-bg3 text-text-secondary",
  accent: "bg-accent/10 text-accent",
  success: "bg-status-success/10 text-status-success",
  warning: "bg-status-warning/10 text-status-warning",
  error: "bg-status-error/10 text-status-error",
};

const NOTE_TONE_CLASS: Record<NoteTone, string> = {
  info: "bg-accent/10 text-accent",
  warning: "bg-status-warning/10 text-status-warning",
  error: "bg-status-error/10 text-status-error",
};

export function ToolResultCard({
  scope,
  signal,
  note,
  noteTone = "warning",
  error,
  children,
}: ToolResultCardProps) {
  /* Error short-circuit — the audit treats {error: true} envelopes as a
     single-purpose state. Renderers route here instead of dumping JSON. */
  if (error) {
    return (
      <div
        data-tool-card="error"
        className="rounded-lg border border-status-error/30 bg-status-error/10 px-3 py-2 text-xs text-status-error"
      >
        <div className="font-semibold uppercase tracking-wider text-label">
          error
        </div>
        <div className="mt-1 text-text-secondary">{error.detail}</div>
      </div>
    );
  }

  const hasScope = scope && scope.length > 0;
  const hasSignal = signal && signal.length > 0;
  const hasNote = typeof note === "string" && note.length > 0;

  return (
    <div
      data-tool-card="ok"
      className="rounded-lg border border-border bg-neutral-bg1 p-2 text-xs"
    >
      {hasScope && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2">
          {scope!.map((b, i) => (
            <span
              key={`${b.label}-${i}`}
              className="rounded bg-neutral-bg3 px-1.5 py-0.5 font-mono text-text-secondary"
            >
              <span className="text-text-muted">{b.label}:</span> {b.value}
            </span>
          ))}
        </div>
      )}
      {hasSignal && (
        <div className="flex flex-wrap items-center gap-1 mb-2">
          {signal!.map((c, i) => (
            <span
              key={`${c.label}-${i}`}
              className={`rounded px-1.5 py-0.5 font-mono text-label ${
                SIGNAL_TONE_CLASS[c.tone ?? "accent"]
              }`}
            >
              {c.label}: {c.value}
            </span>
          ))}
        </div>
      )}
      {hasNote && (
        <div
          className={`mb-2 rounded px-2 py-1 text-label ${NOTE_TONE_CLASS[noteTone]}`}
        >
          {note}
        </div>
      )}
      {children}
    </div>
  );
}
