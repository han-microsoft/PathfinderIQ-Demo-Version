/**
 * RateLimitOverlay — transparent countdown overlay shown during LLM rate limiting.
 *
 * Purpose:
 *   Displays a floating pill in the top-left corner with a spinning hourglass
 *   and countdown timer when the backend is rate-limited and waiting to retry.
 *   Disappears automatically when tokens resume.
 *
 * Isolation:
 *   Reads ``rateLimitCountdown`` from chatStore only. No side effects.
 *   Pure rendering — cannot affect chat, session, or observability.
 *
 * Dependents:
 *   Rendered by App.tsx (fixed position, always available)
 */

import { useEffect, useState } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useTranslation } from "@/hooks/useTranslation";

/**
 * Floating countdown pill — appears top-left when rate-limited.
 * Shows a spinning hourglass + seconds remaining. Fades in/out.
 */
export function RateLimitOverlay() {
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const rateLimitCountdown = useChatStore((s) => s.getSlice(activeAgentId).rateLimitCountdown);
  /* Local countdown that ticks every second */
  const [remaining, setRemaining] = useState<number | null>(null);

  /* Start the local countdown when rateLimitCountdown changes */
  useEffect(() => {
    if (rateLimitCountdown === null || rateLimitCountdown <= 0) {
      setRemaining(null);
      return;
    }
    setRemaining(rateLimitCountdown);
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
  }, [rateLimitCountdown]);

  if (remaining === null) return null;
  const { t } = useTranslation();

  return (
    <div className="fixed top-16 left-6 z-50 flex items-center gap-3 px-5 py-3 rounded-xl bg-neutral-bg2/80 backdrop-blur-sm border border-border shadow-lg animate-fade-in">
      {/* Spinning hourglass */}
      <span className="text-xl animate-spin-slow">⏳</span>
      {/* Countdown text */}
      <div className="text-sm">
        <span className="text-text-muted">{t("rateLimit.retrying")} </span>
        <span className="font-mono font-bold text-text-primary text-base">
          {remaining}s
        </span>
      </div>
    </div>
  );
}
