/**
 * ObservabilityPanel — resizable bottom panel wrapping the tabbed log streams.
 *
 * Purpose:
 *   Provides a collapsible, vertically resizable panel that sits below the
 *   ChatPanel in the main layout.  Uses the existing ``useResizable`` hook
 *   for drag-to-resize with localStorage persistence.
 *
 *   Wrapped in a React error boundary so any render failure in the
 *   observability UI cannot crash the chat panel above.
 *
 * Isolation:
 *   Mounted as a sibling to ChatPanel in App.tsx (never a child of ChatPanel).
 *   No imports from chat, session, chatStore, or sessionStore.
 *
 * Key collaborators:
 *   - hooks/useResizable.ts — drag-to-resize (already exists)
 *   - TabbedLogStream.tsx — tab bar + log/metadata views
 *   - stores/observabilityStore.ts — visibility state
 *
 * Dependents:
 *   Called by: App.tsx
 */

import { Component, type ReactNode } from "react";
import { useResizable } from "@/hooks/useResizable";
import { TabbedLogStream } from "./TabbedLogStream";

/** Default panel height in pixels. */
const DEFAULT_HEIGHT = 200;

/**
 * Resizable bottom panel for observability log streams and metadata.
 *
 * Drag the top edge to resize.  Height is persisted to localStorage
 * under key ``obs-panel-h``.
 */
export function ObservabilityPanel() {
  /* Resize from the top edge (invert = true: dragging up increases height) */
  const { size: height, handleProps } = useResizable("y", {
    initial: DEFAULT_HEIGHT,
    min: 0,
    max: Infinity,
    storageKey: "obs-panel-h",
    invert: true,
  });

  return (
    <ObservabilityErrorBoundary>
      <div
        className="flex flex-col border-t border-border bg-neutral-bg1"
        style={{ height, flexShrink: 0 }}
      >
        {/* Resize handle — drag to resize panel height */}
        <div
          {...handleProps}
          className="h-2.5 cursor-row-resize shrink-0
                     bg-neutral-bg3 hover:bg-neutral-bg4 active:bg-brand/20
                     transition-colors z-10 flex items-center justify-center group/handle"
        >
          <div className="w-10 h-1 rounded-full bg-neutral-bg5
                          group-hover/handle:bg-brand/70 transition-colors" />
        </div>

        {/* Tabbed content — fills remaining panel height */}
        <div className="flex-1 min-h-0 overflow-hidden">
          <TabbedLogStream />
        </div>
      </div>
    </ObservabilityErrorBoundary>
  );
}

/**
 * Error boundary that catches render failures in observability components.
 *
 * Prevents observability bugs from crashing the entire app / chat panel.
 * Shows a minimal fallback message instead.
 */
class ObservabilityErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-20 flex items-center justify-center text-text-muted text-xs border-t border-border bg-neutral-bg1">
          Observability panel encountered an error.
        </div>
      );
    }
    return this.props.children;
  }
}
