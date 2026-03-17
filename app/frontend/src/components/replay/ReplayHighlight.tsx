/**
 * ReplayHighlight — in-context callout during demo replay.
 *
 * Renders a floating tooltip above a highlighted tool card with a
 * straight SVG arrow connecting them. No backdrop dimming — both the
 * chat and graph panels stay fully visible.
 *
 * The target element is located via `data-tool-id` attribute matching.
 * The tooltip floats in the graph/map area above the chat panel.
 *
 * @collaborators
 *   - stores/replayStore.ts         — reads activeHighlight, calls dismissHighlight
 *   - components/chat/ToolCallDisplay — supplies data-tool-id on tool cards
 *   - features/replay/replayEngine   — emits "highlight" events that trigger this
 */

import { useEffect, useState, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useReplayStore } from "@/stores/replayStore";
import { useTranslation } from "@/hooks/useTranslation";

/* ── Glow ring CSS (injected once) ───────────────────────────────────────── */

const GLOW_CLASS = "replay-highlight-glow";
const GLOW_STYLE_ID = "replay-highlight-glow-style";

function ensureGlowStyle() {
  if (document.getElementById(GLOW_STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = GLOW_STYLE_ID;
  style.textContent = `
    .${GLOW_CLASS} {
      outline: 3px solid #10b981 !important;
      outline-offset: 2px;
      box-shadow: 0 0 20px rgba(16, 185, 129, 0.4), 0 0 40px rgba(16, 185, 129, 0.15) !important;
      animation: replay-glow-pulse 1.5s ease-in-out infinite;
      position: relative;
      z-index: 20;
    }
    @keyframes replay-glow-pulse {
      0%, 100% { box-shadow: 0 0 20px rgba(16, 185, 129, 0.4), 0 0 40px rgba(16, 185, 129, 0.15); }
      50% { box-shadow: 0 0 30px rgba(16, 185, 129, 0.6), 0 0 60px rgba(16, 185, 129, 0.25); }
    }
  `;
  document.head.appendChild(style);
}

/* ── Safe DOM lookup (IDs may contain quotes/brackets) ───────────────────── */

function findToolElement(targetId: string): Element | null {
  const all = document.querySelectorAll("[data-tool-id]");
  for (const el of all) {
    if (el.getAttribute("data-tool-id") === targetId) return el;
  }
  return null;
}

/** Walk up the DOM to find the nearest scrollable ancestor. */
function findScrollParent(el: Element): Element | null {
  let node: Element | null = el.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    if (
      style.overflowY === "auto" ||
      style.overflowY === "scroll" ||
      style.overflow === "auto" ||
      style.overflow === "scroll"
    ) {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

/* ── Component ───────────────────────────────────────────────────────────── */

interface Coords {
  targetTop: number;
  targetCenterX: number;
  tooltipTop: number;
  tooltipLeft: number;
}

export function ReplayHighlight() {
  const highlight = useReplayStore((s) => s.activeHighlight);
  const dismiss = useReplayStore((s) => s.dismissHighlight);
  const { t } = useTranslation();

  const tooltipRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [ready, setReady] = useState(false);

  /* Compute tooltip position relative to the target element. */
  const reposition = useCallback(() => {
    if (!highlight) return;
    const el = findToolElement(highlight.targetId);
    if (!el) return;

    const rect = el.getBoundingClientRect();
    const tooltipW = 360;
    const tooltipH = tooltipRef.current?.getBoundingClientRect().height ?? 220;
    const gap = 20;

    const targetCenterX = rect.left + rect.width / 2;
    let tooltipLeft = targetCenterX - tooltipW / 2;
    tooltipLeft = Math.max(16, Math.min(tooltipLeft, window.innerWidth - tooltipW - 16));

    let tooltipTop = rect.top - tooltipH - gap;
    if (tooltipTop < 8) tooltipTop = 8;

    setCoords({ targetTop: rect.top, targetCenterX, tooltipTop, tooltipLeft });
    setReady(true);
  }, [highlight]);

  /* On highlight change: scroll target into view, apply glow, compute position. */
  useEffect(() => {
    if (!highlight) {
      setCoords(null);
      setReady(false);
      return;
    }
    ensureGlowStyle();

    /* Two-phase approach: first scroll, then position after scroll settles. */
    let cancelled = false;

    const t1 = setTimeout(() => {
      if (cancelled) return;
      const el = findToolElement(highlight.targetId);
      if (!el) {
        console.warn("[ReplayHighlight] target not found:", highlight.targetId);
        return;
      }
      /* Auto-expand the tool card so the result is visible. */
      el.dispatchEvent(new CustomEvent("replay-expand"));
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add(GLOW_CLASS);
    }, 50);

    /* Wait for scroll to finish, then measure and show. */
    const t2 = setTimeout(() => {
      if (cancelled) return;
      reposition();
    }, 550);

    return () => {
      cancelled = true;
      clearTimeout(t1);
      clearTimeout(t2);
      document.querySelectorAll(`.${GLOW_CLASS}`).forEach((el) =>
        el.classList.remove(GLOW_CLASS),
      );
      setReady(false);
      setCoords(null);
    };
  }, [highlight, reposition]);

  /* Reposition on window resize and on scroll within the chat container. */
  useEffect(() => {
    if (!highlight) return;

    const el = findToolElement(highlight.targetId);
    const scrollParent = el ? findScrollParent(el) : null;

    const handler = () => reposition();
    window.addEventListener("resize", handler);
    /* Track scroll so the tooltip stays pinned to the tool card. */
    if (scrollParent) {
      scrollParent.addEventListener("scroll", handler, { passive: true });
    }

    return () => {
      window.removeEventListener("resize", handler);
      if (scrollParent) {
        scrollParent.removeEventListener("scroll", handler);
      }
    };
  }, [highlight, reposition]);

  /* Nothing active — render nothing. */
  if (!highlight) return null;

  /* Arrow geometry (only when fully positioned). */
  const tooltipW = 360;
  const arrowStartX = coords ? coords.tooltipLeft + tooltipW / 2 : 0;
  const tooltipH = tooltipRef.current?.getBoundingClientRect().height ?? 220;
  const arrowStartY = coords ? coords.tooltipTop + tooltipH : 0;
  const arrowEndX = coords?.targetCenterX ?? 0;
  const arrowEndY = coords ? coords.targetTop - 4 : 0;
  const showArrow = ready && coords && arrowEndY > arrowStartY + 8;

  return createPortal(
    <>
      {/* Arrow SVG — viewport-sized, pointer-events none */}
      {showArrow && (
        <svg
          style={{
            position: "fixed",
            inset: 0,
            width: "100vw",
            height: "100vh",
            pointerEvents: "none",
            zIndex: 9998,
          }}
        >
          <defs>
            <marker
              id="replay-arrow-head"
              viewBox="0 0 10 10"
              refX="5"
              refY="10"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 5 10 L 10 0" fill="#10b981" />
            </marker>
          </defs>
          <line
            x1={arrowStartX}
            y1={arrowStartY}
            x2={arrowEndX}
            y2={arrowEndY}
            stroke="#10b981"
            strokeWidth={2}
            strokeDasharray="6 4"
            markerEnd="url(#replay-arrow-head)"
          />
        </svg>
      )}

      {/* Tooltip — always mounted so ref can measure; hidden until positioned */}
      <div
        ref={tooltipRef}
        style={{
          position: "fixed",
          top: coords?.tooltipTop ?? -9999,
          left: coords?.tooltipLeft ?? -9999,
          width: tooltipW,
          zIndex: 9999,
          opacity: ready ? 1 : 0,
          transition: "opacity 0.2s ease-in",
          pointerEvents: ready ? "auto" : "none",
        }}
        className="rounded-xl border border-emerald-500/40 bg-neutral-bg2 shadow-2xl
                    ring-1 ring-emerald-500/20"
      >
        {/* Emerald accent bar at the top */}
        <div className="h-1 rounded-t-xl bg-gradient-to-r from-emerald-500 to-teal-400" />

        <div className="px-5 py-4 space-y-3">
          <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
            <span className="text-base">💡</span>
            {highlight.title}
          </h3>

          <p className="text-sm text-text-secondary leading-relaxed">
            {highlight.body}
          </p>

          <button
            onClick={dismiss}
            className="w-full py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500
                       active:bg-emerald-700 text-white text-sm font-semibold
                       transition-colors cursor-pointer"
          >
            {t("replay.gotIt")}
          </button>
        </div>
      </div>
    </>,
    document.body,
  );
}
