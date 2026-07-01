/**
 * @module ToolCallDisplay
 *
 * Collapsible tool invocation card — renders a single tool call within
 * an assistant message bubble.
 *
 * Displays a compact header row with an emoji icon (mapped from
 * `TOOL_ICONS`), the tool name in monospace, and a status indicator:
 *   - `running`  — pulsing brand-colour dot + "Running…" label
 *   - `complete` — green check icon + one-line result summary
 *   - `error`    — red X icon + error description
 *
 * Clicking the header toggles an expand/collapse transition to reveal
 * the full tool arguments (JSON) and result payload (JSON) in
 * syntax-highlighted `<pre>` blocks.
 *
 * @props
 *   - `toolCall`    — the {@link ToolCall} object (name, arguments, result, status)
 *   - `isStreaming`  — whether the parent message is still streaming (affects status logic)
 *
 * @collaborators
 *   - lucide-react icons (CheckCircle2, XCircle, ChevronDown, ChevronRight)
 *
 * @dependents
 *   Rendered by {@link MessageBubble} for each `type: 'tool_call'` ContentPart.
 */

import { useState, useRef, useEffect, memo } from "react";
import { useAgentStore } from "@/stores/agentStore";
import {
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { ToolCall } from "@/api/types";
import { getAgentHeadshot } from "@/utils/agentHeadshots";
import { getToolResultRenderer, getToolArgsRenderer, ArgumentsGrid } from "./tool-renderers";
import { ThinkingDisplay } from "./tool-renderers/ThinkingDisplay";
import { CallEngineerRenderer } from "./CallEngineerRenderer";
import { useTranslation } from "@/hooks/useTranslation";

interface ToolCallDisplayProps {
  toolCall: ToolCall;
  isStreaming?: boolean;
}

const TOOL_ICONS: Record<string, string> = {
  thinking: "💭",
  query_graph: "🔍",
  query_telemetry: "📊",
  query_alerts: "🚨",
  search_runbooks: "📚",
  search_tickets: "🎫",
  search_equipment: "🧰",
  search_infra_specs: "📐",
  dispatch_field_engineer: "🚀",
  call_engineer: "📞",
  reroute_traffic: "🔀",
  set_link_status: "🚦",
  create_incident_ticket: "🎫",
  update_advisory: "📣",
  estimate_blast_radius: "💥",
  send_incident_report: "📧",
  ask_work_iq: "💼",
  delegate_to_agent: "🤖",
};

export const ToolCallDisplay = memo(function ToolCallDisplay({
  toolCall,
  isStreaming = false,
}: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const icon = TOOL_ICONS[toolCall.name] ?? "\uD83D\uDD27";
  const hasResult = !!toolCall.result;
  const isRunning = toolCall.status === "running" || (isStreaming && !hasResult);
  const isError = toolCall.status === "error";
  const hasArgs = Object.keys(toolCall.arguments).length > 0;
  const { t } = useTranslation();

  /* Auto-expand when a replay highlight targets this card. */
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const handler = () => setExpanded(true);
    el.addEventListener("replay-expand", handler);
    return () => el.removeEventListener("replay-expand", handler);
  }, []);

  // Live timer for running tool calls — uses toolCall.start_ms so the
  // elapsed time persists across tab switches (component unmount/remount).
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (isRunning && !toolCall.duration_ms) {
      // Use the persisted start timestamp from the store, not Date.now().
      // This prevents the timer from resetting to 0 on tab switch.
      const start = toolCall.start_ms ?? Date.now();
      // Set initial elapsed immediately (non-zero on remount)
      setElapsedMs(Date.now() - start);
      intervalRef.current = setInterval(() => setElapsedMs(Date.now() - start), 100);
      return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isRunning, toolCall.duration_ms, toolCall.start_ms]);

  // Duration to display: persisted duration_ms, or live elapsed
  const displayDuration = toolCall.duration_ms ?? (isRunning ? elapsedMs : null);

  // Special rendering for the thinking tool — inline thought bubble
  if (toolCall.name === "thinking") {
    const thoughts = (toolCall.arguments.thoughts as string) ?? "";
    return <div data-tool-id={toolCall.id}><ThinkingDisplay thoughts={thoughts} /></div>;
  }

  // Special rendering for call_engineer — Teams-style calling card
  if (toolCall.name === "call_engineer") {
    const engineerName = (toolCall.arguments.engineer_name as string) ?? "Unknown";
    const engineerPhone = (toolCall.arguments.engineer_phone as string) ?? "Unknown";
    return (
      <div data-tool-id={toolCall.id}>
        <CallEngineerRenderer
          engineerName={engineerName}
          engineerPhone={engineerPhone}
          isRunning={isRunning}
        />
      </div>
    );
  }

  // Extract agent_id from delegation tool arguments (for "View Tab" button)
  const delegationAgentId = toolCall.name === "delegate_to_agent"
    ? (toolCall.arguments.agent_id as string) ?? null
    : null;

  // For delegate_to_agent, resolve the target agent's headshot
  const agents = useAgentStore((s) => s.agents);
  const delegationAgent = delegationAgentId
    ? agents.find((a) => a.id === delegationAgentId)
    : null;
  const delegationIcon = delegationAgent
    ? (delegationAgent.headshot_url ?? getAgentHeadshot(delegationAgent.name))
    : (delegationAgentId ? getAgentHeadshot(delegationAgentId) : null);

  return (
    <div ref={rootRef} data-tool-id={toolCall.id} className="my-1 rounded-lg border border-border bg-neutral-bg2 overflow-hidden transition-all [font-size:inherit]">
      {/* Header row */}
      <div className="flex items-center">
        {/* View Tab button — delegation tool only */}
        {delegationAgentId && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              useAgentStore.getState().viewDelegatedTab(delegationAgentId);
            }}
            className="shrink-0 px-3 py-2.5 text-[0.75em] font-medium text-brand hover:bg-brand/10 border-r border-border transition-colors"
            title={`Switch to ${delegationAgentId} tab`}
          >
            {t("tool.viewTab")}
          </button>
        )}

        {/* Expand/collapse toggle — rest of header */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex flex-1 items-center gap-2 px-3 py-2.5 hover:bg-neutral-bg3 transition-colors text-left min-w-0"
        >
        {delegationIcon ? (
          <img
            src={delegationIcon}
            alt=""
            className="h-10 w-10 rounded-full object-cover shrink-0"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <span className="shrink-0">{icon}</span>
        )}
        <span className="font-mono font-medium text-text-primary truncate">
          {toolCall.name}
        </span>

        {/* Duration timer */}
        {displayDuration != null && (
          <span className="text-[0.8em] font-mono text-text-muted tabular-nums">
            {(displayDuration / 1000).toFixed(1)}s
          </span>
        )}

        {/* Status indicator */}
        {isRunning && (
          <span className="ml-auto flex items-center gap-1.5 text-[0.85em] text-brand">
            <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            {t("tool.running")}
          </span>
        )}
        {hasResult && !isError && (
          <>
            <CheckCircle2 className="h-3.5 w-3.5 text-status-success shrink-0 ml-auto" />
            {toolCall.summary && (
              <span className="text-[0.85em] text-text-muted truncate max-w-[200px]">
                {toolCall.summary}
              </span>
            )}
          </>
        )}
        {isError && (
          <>
            <XCircle className="h-3.5 w-3.5 text-status-error shrink-0 ml-auto" />
            {toolCall.summary && (
              <span className="text-[0.85em] text-status-error truncate max-w-[200px]">
                {toolCall.summary}
              </span>
            )}
          </>
        )}

        {/* Chevron */}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-text-muted shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-text-muted shrink-0" />
        )}
      </button>
      </div>

{/* Expandable detail — uses specialized renderers */}
      {expanded && (
        <div className="border-t border-border px-3 py-2.5 space-y-2">
          {/* Arguments — custom renderer or clean key-value grid */}
          {hasArgs && (
            <div>
              <span className="text-[0.7em] font-medium text-text-muted uppercase tracking-wider">
                {t("tool.arguments")}
              </span>
              <div className="mt-1 rounded bg-neutral-bg1 p-2">
                {(() => {
                  const ArgsRenderer = getToolArgsRenderer(toolCall.name);
                  return ArgsRenderer
                    ? <ArgsRenderer args={toolCall.arguments} />
                    : <ArgumentsGrid args={toolCall.arguments} />;
                })()}
              </div>
            </div>
          )}

          {/* Result — dispatched to specialized renderer by tool name */}
          {hasResult && (
            <div>
              <span
                className={`text-[0.7em] font-medium uppercase tracking-wider ${
                  isError ? "text-status-error" : "text-status-success"
                }`}
              >
                {t("tool.result")}
              </span>
              <div className="mt-1">
                {(() => {
                  const Renderer = getToolResultRenderer(toolCall.name);
                  return <Renderer result={toolCall.result!} />;
                })()}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
