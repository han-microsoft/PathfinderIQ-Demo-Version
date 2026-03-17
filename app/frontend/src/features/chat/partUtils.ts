/**
 * Chat part utilities — pure functions for content part transformations.
 *
 * Module role:
 *   Shared logic for converting between server message formats and the
 *   frontend's ContentPart rendering model. Extracted from chatStore.ts
 *   and MessageBubble.tsx to eliminate duplication.
 *
 * Functions:
 *   - legacyToParts()        — converts old messages (no parts array) to ContentPart[]
 *   - generateToolSummary()  — produces a one-line summary from tool result JSON
 *
 * Key collaborators:
 *   - api/types.ts — Message, ContentPart, ToolCall types
 *
 * Dependents:
 *   - stores/chatStore.ts         — calls both functions
 *   - components/chat/MessageBubble.tsx — calls legacyToParts
 */

import type { Message, ContentPart, ToolCall } from "@/api/types";

/**
 * Generate a one-line summary from a tool's result JSON.
 *
 * Recognizes common response shapes:
 *   - error responses → "✗ <detail>"
 *   - tabular (columns + data/rows) → "✓ N rows"
 *   - search results → "✓ N results"
 *   - dispatch → "✓ <dispatch_id>"
 *   - other JSON → "✓ Complete"
 *   - non-JSON → truncated raw string
 *
 * @param _name - tool name (unused, reserved for future per-tool customization)
 * @param result - raw result string (typically JSON)
 * @returns one-line summary string
 */
export function generateToolSummary(_name: string, result: string): string {
  try {
    const parsed = JSON.parse(result);
    if (parsed.error) {
      const detail = parsed.detail ?? "Error";
      return `✗ ${typeof detail === "string" ? detail.slice(0, 80) : "Error"}`;
    }
    if (parsed.columns && parsed.data) return `✓ ${parsed.data.length} rows`;
    if (parsed.columns && parsed.rows) return `✓ ${parsed.rows.length} rows`;
    if (parsed.results) return `✓ ${parsed.count ?? parsed.results.length} results`;
    if (parsed.dispatch_id) return `✓ ${parsed.dispatch_id}`;
    return "✓ Complete";
  } catch {
    return result.length > 60 ? result.slice(0, 60) + "…" : result;
  }
}

/**
 * Reconstruct ContentPart[] from a server-persisted message that lacks parts.
 *
 * The server stores raw content plus tool_calls. This function rebuilds
 * the interleaved parts array so switching sessions preserves rendering.
 * Tool calls with a result are marked "complete"; those without are "pending".
 * Text content is trimmed and appended after tool_call parts.
 *
 * @param msg - the Message object (may have empty parts array)
 * @returns ordered ContentPart array for rendering
 */
export function legacyToParts(msg: Message): ContentPart[] {
  const parts: ContentPart[] = [];
  const toolCalls = msg.tool_calls ?? [];
  const content = msg.content ?? "";

  /* Tool call parts first — preserves the chronological order */
  for (const tc of toolCalls) {
    parts.push({
      type: "tool_call",
      toolCall: { ...tc, status: tc.result ? "complete" : "pending" } as ToolCall,
    });
  }

  /* Text content last */
  if (content) {
    const trimmed = content.trim();
    if (trimmed) parts.push({ type: "text", text: trimmed });
  }

  return parts;
}
