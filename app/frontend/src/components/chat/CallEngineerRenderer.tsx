/**
 * CallEngineerRenderer — Teams-style phone call overlay for the
 * ``call_engineer`` tool.
 *
 * Module role:
 *   Renders a self-contained calling card that handles every lifecycle
 *   state of the call_engineer tool:
 *
 *   1. **Ringing** (tool running) — pulsing avatar, "Calling..." label,
 *      Web Audio ring tone plays automatically.
 *   2. **No answer** (tool result received) — static avatar, red "didn't
 *      pick up" message, and a "Call Again" button.
 *   3. **Re-ringing** (Call Again clicked) — same as ringing, but driven
 *      by client-side state (no backend round-trip). Resolves back to
 *      state 2 after two ring cycles.
 *
 *   On session restore (persisted messages), the component renders in
 *   state 2 immediately — no auto-ring, no audio. The Call Again button
 *   remains functional.
 *
 * Key collaborators:
 *   - ToolCallDisplay.tsx — special-cases ``call_engineer`` to render this
 *     component instead of the generic expand/collapse card.
 *   - ringTone.ts — Web Audio ring tone synthesis.
 *   - chatStore.ts / legacyToParts — restores tool call state from sessions.
 *
 * Dependents:
 *   Rendered by: ToolCallDisplay.tsx (inline, not via renderer registry).
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { Phone, PhoneOff, PhoneMissed } from "lucide-react";
import { playRingTone } from "./tool-renderers/ringTone";

/* ── Props ─────────────────────────────────────────────────────────────── */

interface CallEngineerRendererProps {
  /** Engineer name from tool arguments. */
  engineerName: string;
  /** Engineer phone number from tool arguments. */
  engineerPhone: string;
  /** Whether the tool is currently executing (backend sleeping = phone ringing). */
  isRunning: boolean;
}

/* ── Initials extractor ────────────────────────────────────────────────── */

/**
 * Extract up to 2 uppercase initials from a name string.
 * Falls back to "?" for empty/unparseable input.
 */
function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0 || !parts[0]) return "?";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

/* ── Component ─────────────────────────────────────────────────────────── */

export function CallEngineerRenderer({
  engineerName,
  engineerPhone,
  isRunning,
}: CallEngineerRendererProps) {
  /**
   * Local re-ring state — true while the Call Again animation is active.
   * Purely client-side; no backend call is made.
   */
  const [isReRinging, setIsReRinging] = useState(false);

  /** Ref to the ring tone cancel function so we can stop audio on unmount / re-ring end. */
  const cancelRef = useRef<(() => void) | null>(null);

  /** Whether the calling animation should play (either live tool run or Call Again). */
  const showRinging = isRunning || isReRinging;

  /* ── Auto-play ring tone while the tool is running (live stream only) ── */
  useEffect(() => {
    if (!isRunning) return;

    /* Play ring tone for 2 cycles — roughly matches the 5s backend sleep. */
    const { promise, cancel } = playRingTone(2);
    cancelRef.current = cancel;

    promise.then(() => {
      cancelRef.current = null;
    });

    /* Cleanup: stop audio if the component unmounts or isRunning flips. */
    return () => {
      cancel();
      cancelRef.current = null;
    };
  }, [isRunning]);

  /* ── Call Again handler ────────────────────────────────────────────── */

  const handleCallAgain = useCallback(() => {
    if (isReRinging) return; // prevent double-clicks
    setIsReRinging(true);

    /* Play 2 ring cycles (~5s), then snap back to "no answer" state. */
    const { promise, cancel } = playRingTone(2);
    cancelRef.current = cancel;

    promise.then(() => {
      setIsReRinging(false);
      cancelRef.current = null;
    });
  }, [isReRinging]);

  /* ── Cleanup on unmount ────────────────────────────────────────────── */
  useEffect(() => {
    return () => {
      if (cancelRef.current) cancelRef.current();
    };
  }, []);

  /* ── Derived values ────────────────────────────────────────────────── */

  const initials = getInitials(engineerName);

  return (
    <div className="my-2 rounded-xl border border-border bg-neutral-bg2 overflow-hidden">
      {/* Compact header row */}
      <div className="flex items-center gap-2 px-3 py-2 bg-neutral-bg3/50">
        <Phone className="h-4 w-4 text-brand" />
        <span className="font-mono font-medium text-text-primary text-sm">
          call_engineer
        </span>
        {showRinging && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-brand">
            <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            Calling…
          </span>
        )}
        {!showRinging && !isRunning && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-status-error">
            <PhoneMissed className="h-3.5 w-3.5" />
            No answer
          </span>
        )}
      </div>

      {/* Calling card body */}
      <div className="flex flex-col items-center py-6 px-4 gap-3">
        {/* Avatar circle with initials — pulses when ringing */}
        <div className="relative">
          <div
            className={`
              w-16 h-16 rounded-full flex items-center justify-center
              text-xl font-bold text-white
              ${showRinging
                ? "bg-brand"
                : "bg-neutral-bg3 text-text-muted"
              }
            `}
          >
            {initials}
          </div>

          {/* Pulsing ring animation — only visible while ringing */}
          {showRinging && (
            <>
              <span className="absolute inset-0 rounded-full border-2 border-brand animate-ping opacity-30" />
              <span
                className="absolute inset-0 rounded-full border-2 border-brand animate-ping opacity-20"
                style={{ animationDelay: "0.5s" }}
              />
            </>
          )}
        </div>

        {/* Engineer name */}
        <span className="text-sm font-semibold text-text-primary">
          {engineerName}
        </span>

        {/* Phone number */}
        <span className="text-xs font-mono text-text-muted">
          {engineerPhone}
        </span>

        {/* Status line */}
        {showRinging ? (
          <div className="flex items-center gap-2 text-sm text-brand mt-1">
            <Phone className="h-4 w-4 animate-bounce" />
            <span>
              Ringing
              <span className="inline-block w-6 text-left animate-pulse">...</span>
            </span>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 mt-1">
            {/* No-answer message */}
            <div className="flex items-center gap-2 text-sm text-status-error">
              <PhoneOff className="h-4 w-4" />
              <span>Recipient didn't pick up</span>
            </div>

            {/* Call Again button */}
            <button
              onClick={handleCallAgain}
              disabled={isReRinging}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                transition-colors
                ${isReRinging
                  ? "bg-neutral-bg3 text-text-muted cursor-not-allowed"
                  : "bg-brand/20 text-brand hover:bg-brand/30 border border-brand/40"
                }
              `}
            >
              <Phone className="h-4 w-4" />
              {isReRinging ? "Calling…" : "Call Again"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
