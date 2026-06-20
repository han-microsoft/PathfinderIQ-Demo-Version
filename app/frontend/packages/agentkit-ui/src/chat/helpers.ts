/**
 * Tool renderer helpers — shared utilities for tool call display components.
 *
 * Module role:
 *   Extracts duplicated patterns from tool renderers:
 *     - severity/urgency badge color mapping
 *     - JSON parse-with-fallback
 *     - canonical table-cell formatter (single source of truth, replaces
 *       the three local copies in TabularResult/GraphResult/GraphEnvelopeResult)
 *     - typed-error extraction for the `<ToolResultCard error>` short-circuit
 *
 * Dependents: tool-renderers/*.tsx
 */

/**
 * Map a severity or urgency level to Tailwind CSS classes for badge rendering.
 *
 * Handles both incident severity (CRITICAL/MAJOR) and dispatch urgency
 * (CRITICAL/HIGH) by checking for the mid-level trigger word.
 *
 * @param level - The severity/urgency string (e.g. "CRITICAL", "MAJOR", "HIGH")
 * @returns Tailwind class string for text + background color
 */
export function severityColor(level: string): string {
  const upper = (level || "").toUpperCase();
  if (upper === "CRITICAL") return "text-status-error bg-status-error/10";
  if (upper === "MAJOR" || upper === "HIGH") return "text-status-warning bg-status-warning/10";
  return "text-text-muted bg-neutral-bg3";
}

/**
 * Safely parse a JSON tool result string.
 *
 * @param result - Raw JSON string from tool execution
 * @returns Parsed object, or null if parsing fails
 */
export function parseToolResult<T = Record<string, unknown>>(result: string): T | null {
  try {
    return JSON.parse(result) as T;
  } catch {
    return null;
  }
}

/**
 * Format a single cell value for a result table.
 *
 * Canonical implementation — TabularResult, GraphResult, and ResultTable
 * all consume this so number formatting / null sentinel / nested-object
 * truncation never drift again.
 */
export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "string") return value;
  const s = JSON.stringify(value);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
}

/**
 * Extract a typed-error envelope from a parsed tool result.
 *
 * Returns the human-readable detail string if the parsed payload
 * carries an error signal (`error: true | string`, or `status: "error"`),
 * otherwise null. Renderers route the return value through
 * `<ToolResultCard error={{ detail }} />`.
 */
export function extractError(parsed: Record<string, unknown> | null): string | null {
  if (!parsed) return null;
  const status = typeof parsed.status === "string" ? parsed.status : null;
  const hasErrorFlag =
    parsed.error === true || (typeof parsed.error === "string" && parsed.error.length > 0);
  if (!hasErrorFlag && status !== "error") return null;
  if (typeof parsed.detail === "string" && parsed.detail.length > 0) return parsed.detail;
  if (typeof parsed.error === "string" && parsed.error.length > 0) return parsed.error;
  if (typeof parsed.note === "string" && parsed.note.length > 0) return parsed.note;
  return "unspecified error";
}
