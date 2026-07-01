/**
 * JsonFallback — last-resort syntax-highlighted JSON dump.
 *
 * Used when:
 *   - No specialised renderer is registered for the tool, OR
 *   - The registered renderer cannot parse the envelope shape.
 *
 * Pair: `ToolResultError` lives here too so renderers have one import
 * for "show raw JSON when shape is unknown" and "show typed error
 * banner when shape carries an explicit error envelope". Both retired
 * three private clones in TabularResult/SearchResultCards/SituationResult.
 */

interface JsonFallbackProps {
  result: string;
}

export function JsonFallback({ result }: JsonFallbackProps) {
  let formatted: string;
  try {
    formatted = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    formatted = result;
  }
  return (
    <pre className="overflow-x-auto rounded bg-neutral-bg1 p-2 text-xs font-mono text-text-secondary max-h-48 overflow-y-auto">
      {formatted}
    </pre>
  );
}

/**
 * ToolResultError — standalone red banner for typed-error envelopes.
 *
 * Renderers prefer the `<ToolResultCard error={{ detail }} />`
 * short-circuit when the entire card should be an error. Use this
 * component only when an error needs to sit inline alongside other
 * content (e.g. within an existing card scaffold the renderer
 * cannot rebuild).
 */
export function ToolResultError({ detail }: { detail: string }) {
  return (
    <div className="rounded-lg border border-status-error/30 bg-status-error/10 px-3 py-2 text-xs text-status-error">
      <div className="font-semibold uppercase tracking-wider text-label">error</div>
      <div className="mt-1 text-text-secondary">{detail}</div>
    </div>
  );
}
