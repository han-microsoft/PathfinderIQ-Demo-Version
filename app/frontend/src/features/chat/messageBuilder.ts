/**
 * Message builder — assembles final Message objects from streaming ContentParts.
 *
 * Module role:
 *   Pure function extracted from chatStore.ts onDone/onAborted/onError
 *   callbacks. All three callbacks build a Message from accumulated
 *   streaming parts with the same logic — only the status field differs.
 *
 * Key collaborators:
 *   - api/types.ts — Message, ContentPart, ToolCall types
 *
 * Dependents:
 *   - stores/chatStore.ts — calls buildAssistantMessage in onDone/onAborted/onError
 */

import type { ContentPart, Message, ToolCall } from "@/api/types";

/**
 * Build a final assistant Message from accumulated streaming parts.
 *
 * Extracts text-type parts and joins them as ``content`` (double newline
 * separator). Extracts tool_call parts into the ``tool_calls`` array.
 * The full ``parts`` array is preserved for interleaved rendering.
 *
 * @param streamingParts — the ordered ContentPart array built during streaming
 * @param agentId — the agent that authored this message (becomes agent_name)
 * @param status — "complete", "aborted", or "error"
 * @returns a fully constructed Message ready to append to the messages array
 */
export function buildAssistantMessage(
  streamingParts: ContentPart[],
  agentId: string,
  status: "complete" | "aborted" | "error",
): Message {
  /* Extract text content — ignores thinking parts (💭 are rendered via parts) */
  const textParts = streamingParts
    .filter(
      (p): p is Extract<ContentPart, { type: "text" }> => p.type === "text",
    )
    .map((p) => p.text);

  /* Extract tool calls for the legacy tool_calls field (backward compat) */
  const toolCalls: ToolCall[] = streamingParts
    .filter(
      (p): p is Extract<ContentPart, { type: "tool_call" }> =>
        p.type === "tool_call",
    )
    .map((p) => p.toolCall);

  /* ID prefix distinguishes aborted messages in the ID sync logic */
  const prefix = status === "aborted" ? "aborted" : "assistant";

  return {
    id: `${prefix}-${Date.now()}`,
    role: "assistant",
    content: textParts.join("\n\n"),
    parts: streamingParts,
    status,
    tool_calls: toolCalls,
    agent_name: agentId,
    created_at: new Date().toISOString(),
  };
}
