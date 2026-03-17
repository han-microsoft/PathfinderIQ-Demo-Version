/**
 * App shell — top-level layout component.
 *
 * Module role:
 *   Composes the three-region layout: Header (fixed top), main content area
 *   (graph + chat), and session sidebar (right). The graph panel is resizable
 *   from its bottom edge. The chat panel fills the remaining vertical space.
 *
 * Layout structure:
 *   ┌──────────┬─────────────────────────────┬───────────────┐
 *   │          │ ResizableGraph (topology)  │               │
 *   │  Header  │   MetricsBar              │  Session      │
 *   │ (sidebar)├─────────────────────────────┤  Sidebar      │
 *   │          │ ChatPanel (messages+input) │               │
 *   └──────────┴─────────────────────────────┴───────────────┘
 *
 * Key collaborators:
 *   - components/layout/Header          — header bar with scenario title
 *   - components/layout/ResizableGraph  — drag-resizable graph container
 *   - components/layout/MetricsBar      — topology stats (node/edge counts)
 *   - components/chat/ChatPanel         — message list + input + metadata
 *   - components/session/SessionSidebar — session list with CRUD actions
 *
 * Dependents:
 *   Rendered by: main.tsx (root component)
 */

import { ChatPanel } from "./components/chat";
import { Header, ResizableGraph } from "./components/layout";
import { ObservabilityPanel } from "./components/observability";
import { useObservabilityStore } from "./stores/observabilityStore";
import { useChatSettingsStore } from "./stores/chatSettingsStore";
import { RateLimitOverlay } from "./components/layout/RateLimitOverlay";
import { WelcomeOverlay } from "./components/layout/WelcomeOverlay";
import { ReplayTourOverlay } from "./components/replay/ReplayTourOverlay";
import { ReplayHighlight } from "./components/replay/ReplayHighlight";
import { DemoButtonHint } from "./components/replay/DemoButtonHint";
import { lazy, Suspense, useEffect } from "react";
import { useResizable } from "./hooks/useResizable";
import { useReadinessStore } from "./stores/readinessStore";

// Lazy-load MetricsBar (graph panel host) — pulls react-force-graph-2d (~150KB)
// which is unnecessary when the graph panel is hidden (default state).
const LazyMetricsBar = lazy(() =>
  import("./components/layout/MetricsBar").then((m) => ({ default: m.MetricsBar }))
);
import { useAgentStore } from "./stores/agentStore";

/**
 * Vertical resize handle — a thin bar with a centred pill grip.
 *
 * Spread ``handleProps`` (from ``useResizable``) onto this element.
 * The pill brightens on hover so users instinctively recognise it
 * as a draggable edge.
 */
function VerticalDragHandle(props: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className="w-4 cursor-col-resize shrink-0
                 bg-neutral-bg3 hover:bg-neutral-bg4 active:bg-brand/20
                 transition-colors flex flex-col items-center justify-center group/vhandle"
    >
      {/* Vertical pill grip */}
      <div className="h-8 w-1 rounded-full bg-neutral-bg5 group-hover/vhandle:bg-brand/70 transition-colors" />
    </div>
  );
}

export default function App() {
  /* Observability panel visibility — isolated from chat/session state */
  const isObsVisible = useObservabilityStore((s) => s.isVisible);
  const uiScale = useChatSettingsStore((s) => s.uiScale);
  const graphVisible = useChatSettingsStore((s) => s.graphVisible);

  /* Load the saved scenario FIRST, then fetch runtime metadata.
     This keeps the frontend's request context aligned with the user's
     active scenario before any follow-up API calls are made. */
  useEffect(() => {
    const r = useReadinessStore.getState().setStatus;
    (async () => {
      /* Fetch agent roster with readiness tracking */
      r("sessions", "loading");
      try {
        r("sessions", "complete");
      } catch { r("sessions", "failed"); }

      r("serviceHealth", "complete");

      r("agents", "loading");
      try {
        await useAgentStore.getState().fetchAgents();
        r("agents", "complete");
      } catch { r("agents", "failed"); }

      /* Graph topology loads lazily via useTopology hook — mark ready.
         The actual graph renders when graphVisible is toggled. */
      r("graphTopology", "complete");

      /* Interface is ready when React has rendered all components */
      r("interface", "complete");
    })();
  }, []);

  /* Apply UI scale as root font-size so all rem-based sizes scale
     proportionally while the flex layout stays viewport-bound. */
  useEffect(() => {
    document.documentElement.style.fontSize = `${uiScale * 100}%`;
    return () => { document.documentElement.style.fontSize = ""; };
  }, [uiScale]);

  /* Horizontal resize for the left nav sidebar (default 220px) */
  const { size: leftW, handleProps: leftHandle } = useResizable("x", {
    initial: 220,
    min: 0,
    max: Infinity,
    storageKey: "nav-sidebar-w",
  });

  return (
    <>
      {/* Welcome/init overlay — shown once on first visit, dismissed to localStorage */}
      <WelcomeOverlay />
      <ReplayTourOverlay />
      <ReplayHighlight />
      <DemoButtonHint />

      <div className="flex h-screen w-screen overflow-hidden bg-neutral-bg1">
      {/* Left: resizable nav sidebar */}
      <Header style={{ width: leftW }} />
      <VerticalDragHandle {...leftHandle} />

      {/* Rate limit countdown — floats top-left when backend is throttled */}
      <RateLimitOverlay />

      {/* Centre column: graph + chat — fills remaining space */}
      <main className="flex-1 min-w-0 flex flex-col min-h-0">
        {/* Graph topology — resizable from bottom edge, collapsible */}
        {graphVisible && (
          <ResizableGraph>
            <Suspense fallback={<div className="h-full bg-neutral-bg2 animate-pulse" />}>
              <LazyMetricsBar />
            </Suspense>
          </ResizableGraph>
        )}

        {/* Chat section */}
        <ChatPanel />

        {/* Observability panel — sibling to ChatPanel, never a child of it.
            Hidden by default; toggled via Header button.
            Isolated: own store, own SSE, own components. */}
        {isObsVisible && <ObservabilityPanel />}
      </main>
    </div>
    </>
  );
}
