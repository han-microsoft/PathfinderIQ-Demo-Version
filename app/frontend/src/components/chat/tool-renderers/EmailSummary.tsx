/**
 * @module EmailSummary
 *
 * Renders the `send_incident_report` tool result as a compact email
 * confirmation card showing message ID, recipients, subject, and severity.
 *
 * @props
 *   - `result` — JSON string from the email tool
 *
 * @dependents
 *   Registered in tool-renderers/index.ts for `send_incident_report`.
 */

import { severityColor as getSeverityColor, parseToolResult } from "./helpers";

interface EmailSummaryProps {
  result: string;
}

export function EmailSummary({ result }: EmailSummaryProps) {
  const parsed = parseToolResult(result);
  if (!parsed) {
    return <pre className="text-xs text-text-muted whitespace-pre-wrap">{result}</pre>;
  }

  const severity = String(parsed.severity ?? "").toUpperCase();
  const badgeClass = getSeverityColor(severity);

  return (
    <div className="space-y-2 text-xs">
      <div className="flex items-center gap-2">
        <span className="text-status-success font-semibold">✓ Report Sent</span>
        <span className="font-mono text-text-muted">{String(parsed.message_id ?? "")}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${badgeClass}`}>
          {severity}
        </span>
      </div>

      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
        <span className="text-text-muted font-medium">To</span>
        <span className="text-text-primary">{String(parsed.to ?? "—")}</span>
        <span className="text-text-muted font-medium">CC</span>
        <span className="text-text-primary">{String(parsed.cc ?? "—")}</span>
        <span className="text-text-muted font-medium">Subject</span>
        <span className="text-text-primary font-medium">{String(parsed.subject ?? "—")}</span>
        <span className="text-text-muted font-medium">Length</span>
        <span className="text-text-primary">{String(parsed.report_length_chars ?? "—")} chars</span>
      </div>
    </div>
  );
}
