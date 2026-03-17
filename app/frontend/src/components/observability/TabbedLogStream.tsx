/**
 * TabbedLogStream — tab bar that switches between Agent, Backend, and Metadata views.
 *
 * Purpose:
 *   Renders a horizontal tab bar and keeps all three views mounted (hidden via
 *   CSS ``display:none`` when inactive).  This avoids SSE reconnects and state
 *   loss when switching tabs.
 *
 * Isolation:
 *   Reads active tab from ``observabilityStore``.  No imports from chat or session.
 *
 * Key collaborators:
 *   - LogStream.tsx — renders Agent and Backend tabs
 *   - MetadataDashboard.tsx — renders Metadata tab
 *   - stores/observabilityStore.ts — active tab state
 *
 * Dependents:
 *   Called by: ObservabilityPanel.tsx
 */

import {
  useObservabilityStore,
  type ObsTab,
} from "@/stores/observabilityStore";
import { useChatSettingsStore, FONT_SIZE_MAP } from "@/stores/chatSettingsStore";
import { LogStream } from "./LogStream";

/** Tab definitions: id, display label, and SSE URL. */
const TABS: { id: ObsTab; label: string; url: string }[] = [
  { id: "agent", label: "Agent", url: "/observability/logs/agent" },
  { id: "frontend", label: "Frontend", url: "/observability/logs/frontend" },
  { id: "backend", label: "Backend", url: "/observability/logs/backend" },
];

/**
 * Tabbed container that renders all three observability views.
 * All views stay mounted — inactive views are hidden via CSS.
 */
export function TabbedLogStream() {
  const activeTab = useObservabilityStore((s) => s.activeTab);
  const setTab = useObservabilityStore((s) => s.setTab);
  const obsFontSizeStep = useChatSettingsStore((s) => s.obsFontSizeStep);
  const increaseObsFontSize = useChatSettingsStore((s) => s.increaseObsFontSize);
  const decreaseObsFontSize = useChatSettingsStore((s) => s.decreaseObsFontSize);
  const obsFontSize = FONT_SIZE_MAP[obsFontSizeStep] ?? "0.875rem";

  return (
    <div className="flex flex-col h-full" style={{ fontSize: obsFontSize }}>
      {/* Tab bar */}
      <div className="flex items-center bg-header-bg border-b border-border px-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setTab(tab.id)}
            className={`px-3 py-1.5 font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-brand text-brand"
                : "border-transparent text-text-muted hover:text-text-primary"
            }`}
          >
            {tab.label}
          </button>
        ))}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Font size controls for observability panel — matches chat bar button style */}
        <button
          onClick={decreaseObsFontSize}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-neutral-bg3 text-text-secondary hover:bg-neutral-bg4 hover:text-text-primary transition-colors text-[10px] font-semibold"
          title="Decrease log font size"
        >
          aA−
        </button>
        <button
          onClick={increaseObsFontSize}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-neutral-bg3 text-text-secondary hover:bg-neutral-bg4 hover:text-text-primary transition-colors text-[10px] font-semibold"
          title="Increase log font size"
        >
          aA+
        </button>
      </div>

      {/* Tab content — all kept mounted, visibility toggled via CSS */}
      <div className="flex-1 min-h-0 relative">
        {/* Agent log stream */}
        <div
          className="absolute inset-0"
          style={{ display: activeTab === "agent" ? "block" : "none" }}
        >
          <LogStream
            url="/observability/logs/agent"
            enabled={activeTab === "agent"}
          />
        </div>

        {/* Frontend console log stream */}
        <div
          className="absolute inset-0"
          style={{ display: activeTab === "frontend" ? "block" : "none" }}
        >
          <LogStream
            url="/observability/logs/frontend"
            enabled={activeTab === "frontend"}
          />
        </div>

        {/* Backend log stream */}
        <div
          className="absolute inset-0"
          style={{ display: activeTab === "backend" ? "block" : "none" }}
        >
          <LogStream
            url="/observability/logs/backend"
            enabled={activeTab === "backend"}
          />
        </div>
      </div>
    </div>
  );
}
