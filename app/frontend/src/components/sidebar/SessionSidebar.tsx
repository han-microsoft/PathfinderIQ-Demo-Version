/**
 * @module SessionSidebar
 *
 * Two-panel right sidebar: Service Health and Conversations.
 * Conversations is a fixed-height collapsible panel.
 *
 * Each panel is a self-contained component in the sidebar/ folder:
 *   - ServiceHealth — live Azure service connectivity indicators
 *   - ConversationList — session CRUD with status dots
 *
 * @dependents
 *   Rendered by App.tsx as the right-hand sidebar.
 */

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { ConversationList } from "./ConversationList";
import { ServiceHealth } from "./ServiceHealth";

export function SessionSidebar({ style }: { style?: React.CSSProperties }) {
  const [conversationsCollapsed, setConversationsCollapsed] = useState(true);

  return (
    <aside
      className="border border-border bg-neutral-bg2 select-none overflow-y-auto"
      style={style}
    >
      {/* Inner wrapper uses min-h-full so flex-1 spacer works inside a scrollable container */}
      <div className="flex flex-col min-h-full">
        {/* Service Health — renders at natural content height */}
        <ServiceHealth />

        {/* Conversations — directly under Service Health */}
        <div className="border-t border-border bg-neutral-bg2 shrink-0">
          {conversationsCollapsed ? (
            <button
              onClick={() => setConversationsCollapsed(false)}
              className="h-11 w-full border-b border-border bg-header-bg px-4 flex items-center justify-between text-left"
              title="Expand conversations"
            >
              <span className="text-[19px] font-semibold text-header-text uppercase tracking-wider">Conversations</span>
              <ChevronDown className="h-4 w-4 text-text-muted" />
            </button>
          ) : (
            <div className="max-h-[45vh] flex flex-col overflow-hidden">
              <ConversationList onCollapse={() => setConversationsCollapsed(true)} />
            </div>
          )}
        </div>

        {/* Spacer pushes note to bottom when content is short */}
        <div className="flex-1" />

        <div className="border-t border-border px-3 py-2 bg-neutral-bg2 shrink-0">
          <div className="p-2 rounded-lg bg-neutral-bg3 border border-border text-sm leading-snug text-text-primary">
            <span className="font-semibold">Note:</span> Fabric Capacity may take some time to spin up after long idle periods.
            If graph queries are still running, please wait.
          </div>
        </div>
      </div>
    </aside>
  );
}
