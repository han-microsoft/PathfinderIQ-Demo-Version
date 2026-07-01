/**
 * WorkIqResult — renders ask_work_iq (Microsoft 365 / Work IQ) results as a
 * clean context card: a small "Work IQ" source header plus the natural-language
 * response in markdown. Kept deliberately simple for a C-suite audience —
 * no raw JSON, no engineer-facing fields.
 *
 * @dependents
 *   Registered in tool-renderers/index.ts for `ask_work_iq`.
 */

import type { ToolResultProps } from "./index";
import { MarkdownRenderer } from "../../shared/MarkdownRenderer";

export function WorkIqResult({ result }: ToolResultProps) {
  let parsed: { status?: string; source_type?: string; response?: string };
  try {
    parsed = JSON.parse(result);
  } catch {
    return <pre className="text-text-muted whitespace-pre-wrap text-[0.85em]">{result}</pre>;
  }

  const { source_type, response } = parsed;

  return (
    <div className="space-y-2">
      {/* Source header */}
      <div className="flex items-center gap-2 text-[0.85em] font-medium">
        <span className="text-brand">◑</span>
        <span className="font-semibold text-text-primary">Work IQ</span>
        {source_type && (
          <span className="text-text-muted">· {source_type}</span>
        )}
      </div>

      {/* Response body in markdown */}
      {response ? (
        <div className="prose prose-invert prose-sm max-w-none text-text-secondary [font-size:inherit]">
          <MarkdownRenderer content={response} />
        </div>
      ) : (
        <p className="text-text-muted italic text-[0.9em]">No matching Microsoft 365 context found.</p>
      )}
    </div>
  );
}
