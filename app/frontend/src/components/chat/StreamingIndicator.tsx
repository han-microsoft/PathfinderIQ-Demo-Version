/**
 * @module StreamingIndicator
 *
 * Real-time streaming visualisation — animated typing indicator shown
 * while the assistant LLM is generating a response.
 *
 * Renders three pulsing dots with staggered `animationDelay` values
 * (0 s, 0.2 s, 0.4 s) using the `animate-pulse-dot` Tailwind utility.
 * Includes `role="status"` and `aria-label` for screen-reader
 * accessibility.
 *
 * @remarks
 * - Stateless, no props — purely presentational.
 * - Uses the `--color-brand` CSS variable for dot color via the
 *   `bg-brand` Tailwind class.
 *
 * @dependents
 *   Rendered by {@link MessageBubble} at the tail of an in-flight
 *   assistant message when streaming parts have not yet arrived.
 */

import { useTranslation } from "@/hooks/useTranslation";

export function StreamingIndicator() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-1 px-4 py-2" role="status" aria-label={t("chat.assistantTyping")}>
      <div className="h-2 w-2 rounded-full bg-brand animate-pulse-dot" style={{ animationDelay: "0s" }} />
      <div className="h-2 w-2 rounded-full bg-brand animate-pulse-dot" style={{ animationDelay: "0.2s" }} />
      <div className="h-2 w-2 rounded-full bg-brand animate-pulse-dot" style={{ animationDelay: "0.4s" }} />
    </div>
  );
}
