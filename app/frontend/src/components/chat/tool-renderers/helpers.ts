/**
 * Tool renderer helpers — shared utilities for tool call display components.
 *
 * Module role:
 *   Extracts duplicated patterns from tool renderers: severity/urgency
 *   badge color mapping and JSON parse-with-fallback. Each renderer
 *   imports from here instead of re-implementing the same logic.
 *
 * Key collaborators:
 *   - IncidentReportArgs.tsx, EmailSummary.tsx, DispatchSummary.tsx — severity badges
 *   - EmailSummary.tsx, DispatchSummary.tsx — JSON parse safety
 *
 * Dependents:
 *   Used by: tool-renderers/*.tsx
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
