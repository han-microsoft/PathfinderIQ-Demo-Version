/**
 * Slice reducers — pure functions for mutating AgentChatSlice streaming state.
 *
 * Module role:
 *   Extracts the duplicated event-handling logic from chatStore's sendMessage
 *   callbacks and handleDelegationEvent into reusable pure functions. Each
 *   function takes a slice, applies a mutation, and returns the partial state
 *   update for Zustand's set().
 *
 *   These functions have zero side effects and zero store dependencies —
 *   they operate only on the plain AgentChatSlice object passed to them.
 *
 * Key collaborators:
 *   - stores/chatStore.ts — calls these from onToken/onToolCallStart/etc.
 *   - features/chat/partUtils.ts — generateToolSummary for tool results
 *   - features/chat/messageBuilder.ts — buildAssistantMessage for finalize
 *
 * Dependents:
 *   Used by: chatStore.ts (sendMessage callbacks + handleDelegationEvent)
 */

import type { ToolCall, ContentPart } from "@/api/types";
import { generateToolSummary } from "@/features/chat/partUtils";

/** Minimal subset of AgentChatSlice needed by reducers. */
export interface SliceState {
  streamingParts: ContentPart[];
  streamingToolIndex: Map<string, number>;
  _toolStartTimes: Map<string, number>;
  hasSeenToolCall: boolean;
  lastEventWasToolResult: boolean;
}

/**
 * Append a text token to the streaming parts.
 * If the last part is text or thinking, appends to it; otherwise pushes
 * a new text part.
 */
export function appendToken(
  parts: ContentPart[],
  token: string,
): { streamingParts: ContentPart[] } {
  const updated = [...parts];
  const last = updated[updated.length - 1];
  if (last && (last.type === "text" || last.type === "thinking")) {
    updated[updated.length - 1] = { ...last, text: last.text + token };
  } else {
    updated.push({ type: "text", text: token });
  }
  return { streamingParts: updated };
}

/**
 * Start a new tool call — creates the ToolCall part and updates indexes.
 */
export function startToolCall(
  s: SliceState,
  id: string,
  name: string,
): Partial<SliceState> {
  const parts = [...s.streamingParts];
  const now = Date.now();
  const toolCall: ToolCall = { id, name, arguments: {}, status: "running", start_ms: now };
  const newIndex = parts.length;
  parts.push({ type: "tool_call", toolCall });
  const toolIndex = new Map(s.streamingToolIndex);
  toolIndex.set(id, newIndex);
  const startTimes = new Map(s._toolStartTimes);
  startTimes.set(id, now);
  return {
    streamingParts: parts,
    streamingToolIndex: toolIndex,
    _toolStartTimes: startTimes,
    hasSeenToolCall: true,
    lastEventWasToolResult: false,
  };
}

/**
 * End a tool call — updates arguments on the existing part.
 */
export function endToolCall(
  s: SliceState,
  id: string,
  args: Record<string, unknown>,
): Partial<SliceState> {
  const idx = s.streamingToolIndex.get(id);
  if (idx === undefined) return {};
  const parts = [...s.streamingParts];
  const part = parts[idx];
  if (!part || part.type !== "tool_call") return {};
  parts[idx] = { type: "tool_call", toolCall: { ...part.toolCall, arguments: args } };
  return { streamingParts: parts };
}

/**
 * Apply a tool result — updates status, summary, duration on the tool call part.
 */
export function applyToolResult(
  s: SliceState,
  id: string,
  name: string,
  result: string,
): Partial<SliceState> {
  const idx = s.streamingToolIndex.get(id);
  if (idx === undefined) return {};
  const parts = [...s.streamingParts];
  const part = parts[idx];
  if (!part || part.type !== "tool_call") return {};
  const isError = result.includes('"error"') && result.includes("true");
  const startTime = s._toolStartTimes.get(id);
  const duration_ms = startTime ? Date.now() - startTime : null;
  parts[idx] = {
    type: "tool_call",
    toolCall: {
      ...part.toolCall,
      result,
      status: isError ? "error" : "complete",
      summary: generateToolSummary(name, result),
      duration_ms,
    },
  };
  return { streamingParts: parts, lastEventWasToolResult: true };
}
