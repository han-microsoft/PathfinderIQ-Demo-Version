/**
 * DelegationArgs — clean renderer for `delegate_to_agent` arguments.
 *
 * Shows the target agent as a badge and renders the (often markdown-shaped)
 * `task` instruction as formatted markdown instead of a raw monospace blob.
 *
 * Registered for delegate_to_agent in tool-renderers/index.ts.
 */

import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";

interface DelegationArgsProps {
  args: Record<string, unknown>;
}

export function DelegationArgs({ args }: DelegationArgsProps) {
  const agentId = typeof args.agent_id === "string" ? args.agent_id : null;
  const task = typeof args.task === "string" ? args.task : null;
  const rest = Object.entries(args).filter(
    ([k]) => k !== "agent_id" && k !== "task",
  );

  return (
    <div className="space-y-2 text-xs">
      {agentId && (
        <div className="flex items-center gap-2">
          <span className="text-text-muted font-medium">to</span>
          <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-brand/10 text-brand">
            {agentId}
          </span>
        </div>
      )}
      {task && (
        <div className="rounded bg-neutral-bg1 p-3 border border-border/30 max-h-[360px] overflow-y-auto">
          <div className="prose-sm">
            <MarkdownRenderer content={task} />
          </div>
        </div>
      )}
      {rest.length > 0 && (
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          {rest.map(([k, v]) => (
            <div key={k} className="contents">
              <span className="text-text-muted font-medium">{k}</span>
              <span className="font-mono text-text-secondary whitespace-pre-wrap break-words">
                {typeof v === "string" ? v : JSON.stringify(v, null, 2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
