/**
 * Tests for buildAssistantMessage() — extracted from chatStore onDone/onAborted.
 *
 * Purpose:
 *   Pins the behavior of assembling a final assistant Message from streaming
 *   ContentParts. Both onDone and onAborted do this identically except for
 *   the status field (complete vs aborted).
 *
 * After extraction:
 *   Import from @/features/chat/messageBuilder and verify these tests pass.
 */
import { describe, it, expect } from "vitest";
import type { ContentPart, ToolCall, Message } from "@/api/types";
import { buildAssistantMessage } from "@/features/chat/messageBuilder";

describe("buildAssistantMessage", () => {
  it("joins text parts with double newline", () => {
    const parts: ContentPart[] = [
      { type: "text", text: "Hello" },
      { type: "text", text: "World" },
    ];
    const msg = buildAssistantMessage(parts, "orchestrator", "complete");
    expect(msg.content).toBe("Hello\n\nWorld");
  });

  it("extracts tool_calls from tool_call parts", () => {
    const tc: ToolCall = {
      id: "tc1",
      name: "query_graph",
      arguments: { q: "SELECT *" },
      result: '{"data":[]}',
      status: "complete",
    };
    const parts: ContentPart[] = [
      { type: "tool_call", toolCall: tc },
      { type: "text", text: "Analysis done" },
    ];
    const msg = buildAssistantMessage(parts, "orchestrator", "complete");
    expect(msg.tool_calls).toHaveLength(1);
    expect(msg.tool_calls[0].name).toBe("query_graph");
    expect(msg.content).toBe("Analysis done");
  });

  it("preserves full parts array for interleaved rendering", () => {
    const parts: ContentPart[] = [
      { type: "thinking", text: "Let me think..." },
      { type: "tool_call", toolCall: { id: "t1", name: "search", arguments: {}, status: "complete" } },
      { type: "text", text: "Result" },
    ];
    const msg = buildAssistantMessage(parts, "investigator", "complete");
    expect(msg.parts).toBe(parts);
    expect(msg.parts).toHaveLength(3);
  });

  it("sets status to 'complete' when called with complete", () => {
    const msg = buildAssistantMessage([], "orchestrator", "complete");
    expect(msg.status).toBe("complete");
    expect(msg.role).toBe("assistant");
  });

  it("sets status to 'aborted' when called with aborted", () => {
    const msg = buildAssistantMessage([], "orchestrator", "aborted");
    expect(msg.status).toBe("aborted");
  });

  it("sets status to 'error' when called with error", () => {
    const msg = buildAssistantMessage([], "orchestrator", "error");
    expect(msg.status).toBe("error");
  });

  it("sets agent_name from agentId parameter", () => {
    const msg = buildAssistantMessage([], "network_investigator", "complete");
    expect(msg.agent_name).toBe("network_investigator");
  });

  it("generates an id with the correct prefix", () => {
    const complete = buildAssistantMessage([], "o", "complete");
    expect(complete.id).toMatch(/^assistant-\d+$/);

    const aborted = buildAssistantMessage([], "o", "aborted");
    expect(aborted.id).toMatch(/^aborted-\d+$/);
  });

  it("handles empty parts array", () => {
    const msg = buildAssistantMessage([], "orchestrator", "complete");
    expect(msg.content).toBe("");
    expect(msg.tool_calls).toEqual([]);
    expect(msg.parts).toEqual([]);
  });

  it("ignores thinking parts in content and tool_calls", () => {
    const parts: ContentPart[] = [
      { type: "thinking", text: "Reasoning..." },
      { type: "text", text: "Final answer" },
    ];
    const msg = buildAssistantMessage(parts, "orchestrator", "complete");
    expect(msg.content).toBe("Final answer");
    expect(msg.tool_calls).toEqual([]);
  });
});
