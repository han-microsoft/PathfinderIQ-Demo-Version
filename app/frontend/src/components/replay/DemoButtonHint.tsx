/**
 * DemoButtonHint — pulsing highlight around the "Play Demo Flow" button
 * with a tooltip, shown after the welcome overlay closes (non-demo path).
 *
 * Dismisses on any click. Does not appear if the user chose "Watch the Demo".
 *
 * @collaborators
 *   - stores/replayStore.ts  — reads showDemoHint, calls dismissDemoHint
 *   - components/layout/Header.tsx — the button has id="demo-flow-button"
 */

import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useReplayStore } from "@/stores/replayStore";
import { useTranslation } from "@/hooks/useTranslation";

export function DemoButtonHint() {
  const show = useReplayStore((s) => s.showDemoHint);
  const dismiss = useReplayStore((s) => s.dismissDemoHint);
  const { t } = useTranslation();

  const [rect, setRect] = useState<DOMRect | null>(null);
  const [fastRect, setFastRect] = useState<DOMRect | null>(null);

  /** Measure both demo buttons. */
  const measure = useCallback(() => {
    const el = document.getElementById("demo-flow-button");
    if (el) setRect(el.getBoundingClientRect());
    const el2 = document.getElementById("fast-replay-button");
    if (el2) setFastRect(el2.getBoundingClientRect());
  }, []);

  /* Measure on mount and on resize. */
  useEffect(() => {
    if (!show) return;
    /* Small delay to ensure the button is rendered after welcome overlay closes. */
    const t = setTimeout(measure, 100);
    window.addEventListener("resize", measure);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", measure);
    };
  }, [show, measure]);

  /* Dismiss on any click. */
  useEffect(() => {
    if (!show) return;
    const handler = () => dismiss();
    /* Use setTimeout so the current click (that dismissed welcome) doesn't
       immediately dismiss this hint too. */
    const t = setTimeout(() => {
      document.addEventListener("click", handler, { once: true });
    }, 200);
    return () => {
      clearTimeout(t);
      document.removeEventListener("click", handler);
    };
  }, [show, dismiss]);

  if (!show || !rect) return null;

  const pad = 6;
  const tooltipW = 260;

  return createPortal(
    <>
      {/* Pulsing ring around the button */}
      <div
        style={{
          position: "fixed",
          top: rect.top - pad,
          left: rect.left - pad,
          width: rect.width + pad * 2,
          height: rect.height + pad * 2,
          borderRadius: 12,
          border: "2px solid #10b981",
          boxShadow: "0 0 20px rgba(16, 185, 129, 0.5), 0 0 40px rgba(16, 185, 129, 0.2)",
          animation: "demo-hint-pulse 1.5s ease-in-out infinite",
          pointerEvents: "none",
          zIndex: 9999,
        }}
      />
      {/* Tooltip for main button */}
      <div
        style={{
          position: "fixed",
          top: rect.top + rect.height / 2,
          left: rect.right + pad + 12,
          transform: "translateY(-50%)",
          width: tooltipW,
          zIndex: 9999,
          pointerEvents: "none",
        }}
        className="rounded-lg border border-emerald-500/40 bg-neutral-bg2 shadow-xl px-3 py-2"
      >
        <p className="text-xs font-semibold text-emerald-400">
          {t("replay.detailedWalkthrough")}
        </p>
      </div>
      {/* Tooltip for fast replay button */}
      {fastRect && (
        <div
          style={{
            position: "fixed",
            top: fastRect.top + fastRect.height / 2,
            left: fastRect.right + pad + 12,
            transform: "translateY(-50%)",
            width: tooltipW,
            zIndex: 9999,
            pointerEvents: "none",
          }}
          className="rounded-lg border border-emerald-500/40 bg-neutral-bg2 shadow-xl px-3 py-2"
        >
          <p className="text-xs font-semibold text-emerald-400">
            {t("replay.fastWalkthrough")}
          </p>
        </div>
      )}
      {/* Inject keyframes */}
      <style>{`
        @keyframes demo-hint-pulse {
          0%, 100% { box-shadow: 0 0 20px rgba(16, 185, 129, 0.5), 0 0 40px rgba(16, 185, 129, 0.2); }
          50% { box-shadow: 0 0 30px rgba(16, 185, 129, 0.7), 0 0 60px rgba(16, 185, 129, 0.3); }
        }
      `}</style>
    </>,
    document.body,
  );
}
