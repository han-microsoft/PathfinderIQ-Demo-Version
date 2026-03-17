/**
 * DelegationResult — renders delegate_to_agent tool results as a formatted
 * specialist report card with agent identity header and markdown body.
 */

import type { ToolResultProps } from "./index";
import { MarkdownRenderer } from "../../shared/MarkdownRenderer";

export function DelegationResult({ result }: ToolResultProps) {
  let parsed: { agent_id?: string; status?: string; response?: string; duration_ms?: number; error?: string };
  try {
    parsed = JSON.parse(result);
  } catch {
    return <pre className="text-text-muted whitespace-pre-wrap text-[0.85em]">{result}</pre>;
  }

  const { agent_id, status, response, duration_ms, error } = parsed;
  const isError = status === "error";
  const durationStr = duration_ms ? `${(duration_ms / 1000).toFixed(1)}s` : "";

  return (
    <div className="space-y-2">
      {/* Header bar */}
      <div className="flex items-center gap-2 text-[0.85em] font-medium">
        <span className="text-brand">🤖</span>
        <span className="font-mono text-text-primary">{agent_id ?? "agent"}</span>
        <span className={`px-1.5 py-0.5 rounded text-[0.8em] font-semibold ${
          isError ? "bg-status-error/10 text-status-error" : "bg-status-success/10 text-status-success"
        }`}>
          {status ?? "unknown"}
        </span>
        {durationStr && (
          <span className="text-text-muted font-mono">{durationStr}</span>
        )}
      </div>

      {/* Response body in markdown */}
      {isError && error ? (
        <p className="text-status-error text-[0.9em]">{error}</p>
      ) : response ? (
        <div className="prose prose-invert prose-sm max-w-none text-text-secondary [font-size:inherit]">
          <MarkdownRenderer content={response} />
        </div>
      ) : (
        <p className="text-text-muted italic text-[0.9em]">No response</p>
      )}
    </div>
  );
}
