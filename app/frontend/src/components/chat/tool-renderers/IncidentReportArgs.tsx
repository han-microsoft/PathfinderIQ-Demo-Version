/**
 * @module IncidentReportArgs
 *
 * Custom arguments renderer for `send_incident_report` tool calls.
 *
 * Instead of dumping the raw `report` markdown string as monospace text,
 * renders it as structured sections: subject line prominently displayed,
 * severity badge, and the full report body as rendered markdown in a
 * scrollable container.
 *
 * @dependents
 *   Registered in tool-renderers/index.ts via TOOL_ARGS_RENDERERS.
 *   Called by ToolCallDisplay.tsx when rendering arguments for send_incident_report.
 */

import { MarkdownRenderer } from "@/components/shared/MarkdownRenderer";
import { severityColor as getSeverityColor } from "./helpers";

interface IncidentReportArgsProps {
  args: Record<string, unknown>;
}

export function IncidentReportArgs({ args }: IncidentReportArgsProps) {
  const subject = String(args.subject ?? "");
  const report = String(args.report ?? "");
  const severity = String(args.severity ?? "CRITICAL").toUpperCase();

  const badgeClass = getSeverityColor(severity);

  return (
    <div className="space-y-3 text-xs">
      {/* Subject + severity header */}
      <div className="flex items-start gap-2">
        <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold ${badgeClass}`}>
          {severity}
        </span>
        <span className="text-text-primary font-medium text-sm leading-snug">
          {subject}
        </span>
      </div>

      {/* Report body — rendered as markdown in a scrollable container */}
      {report && (
        <div className="rounded bg-neutral-bg1 p-3 max-h-[400px] overflow-y-auto border border-border/30">
          <div className="prose-sm">
            <MarkdownRenderer content={report} />
          </div>
        </div>
      )}
    </div>
  );
}
