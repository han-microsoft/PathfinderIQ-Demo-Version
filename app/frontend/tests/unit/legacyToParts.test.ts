/**
 * Pre-refactor regression tests for legacyToParts().
 *
 * Purpose:
 *   Pins the current behavior of legacyToParts() before it is
 *   extracted from chatStore.ts into features/chat/partUtils.ts.
 *   This function is duplicated in both chatStore.ts and MessageBubble.tsx.
 *   During refactor, both copies are replaced by a single shared import.
 *
 * After extraction:
 *   1. Update the import to features/chat/partUtils.ts
 *   2. Delete the inline copy below.
 *   3. All tests must still pass.
 */
import { describe, it, expect } from "vitest";
import { legacyToParts } from "@/features/chat/partUtils";
import type { Message, ContentPart, ToolCall } from "@/api/types";

/* ── Factory helper ── */
function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    role: "assistant",
    content: "",
    parts: [],
    status: "complete",
    tool_calls: [],
    agent_name: "orchestrator",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function makeTc(overrides: Partial<ToolCall> = {}): ToolCall {
  return {
    id: "tc-1",
    name: "query_graph",
    arguments: {},
    result: null,
    status: "pending",
    ...overrides,
  };
}

describe("legacyToParts", () => {
  it("returns empty array for message with no content and no tool_calls", () => {
    const msg = makeMsg({ content: "", tool_calls: [] });
    expect(legacyToParts(msg)).toEqual([]);
  });

  it("converts plain text content to a text part", () => {
    const msg = makeMsg({ content: "Hello world" });
    const parts = legacyToParts(msg);
    expect(parts).toHaveLength(1);
    expect(parts[0]).toEqual({ type: "text", text: "Hello world" });
  });

  it("trims whitespace-only content (returns empty)", () => {
    const msg = makeMsg({ content: "   \n\n  " });
    expect(legacyToParts(msg)).toEqual([]);
  });

  it("converts tool_calls with result to complete status", () => {
    const tc = makeTc({ result: '{"data": [1]}' });
    const msg = makeMsg({ tool_calls: [tc] });
    const parts = legacyToParts(msg);
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe("tool_call");
    if (parts[0].type === "tool_call") {
      expect(parts[0].toolCall.status).toBe("complete");
      expect(parts[0].toolCall.result).toBe('{"data": [1]}');
    }
  });

  it("converts tool_calls without result to pending status", () => {
    const tc = makeTc({ result: null });
    const msg = makeMsg({ tool_calls: [tc] });
    const parts = legacyToParts(msg);
    if (parts[0].type === "tool_call") {
      expect(parts[0].toolCall.status).toBe("pending");
    }
  });

  it("places tool_call parts before text part", () => {
    const tc = makeTc({ result: "done" });
    const msg = makeMsg({ content: "Analysis complete", tool_calls: [tc] });
    const parts = legacyToParts(msg);
    expect(parts).toHaveLength(2);
    expect(parts[0].type).toBe("tool_call");
    expect(parts[1].type).toBe("text");
  });

  it("handles multiple tool calls", () => {
    const tc1 = makeTc({ id: "tc-1", name: "query_graph", result: "r1" });
    const tc2 = makeTc({ id: "tc-2", name: "search_runbooks", result: null });
    const msg = makeMsg({ tool_calls: [tc1, tc2] });
    const parts = legacyToParts(msg);
    expect(parts).toHaveLength(2);
    if (parts[0].type === "tool_call") {
      expect(parts[0].toolCall.status).toBe("complete");
    }
    if (parts[1].type === "tool_call") {
      expect(parts[1].toolCall.status).toBe("pending");
    }
  });

  it("preserves tool call arguments and name", () => {
    const tc = makeTc({
      name: "query_graph",
      arguments: { query: "SELECT *" },
      result: "ok",
    });
    const msg = makeMsg({ tool_calls: [tc] });
    const parts = legacyToParts(msg);
    if (parts[0].type === "tool_call") {
      expect(parts[0].toolCall.name).toBe("query_graph");
      expect(parts[0].toolCall.arguments).toEqual({ query: "SELECT *" });
    }
  });
});
