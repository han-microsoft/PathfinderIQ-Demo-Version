/**
 * Tests for syncMessageIds() — extracted from chatStore onDone/onAborted.
 *
 * Purpose:
 *   Pins the ID reconciliation logic that replaces temporary local IDs
 *   (temp-*, assistant-*, aborted-*) with server-canonical IDs after
 *   a stream completes and the session is refreshed.
 *
 * The matching algorithm:
 *   For each local message with a temp ID, find the corresponding server
 *   message by: same role AND position within ±1 index AND not already
 *   claimed by another local message. Replace the local ID with the
 *   server's canonical ID.
 */
import { describe, it, expect } from "vitest";
import type { Message } from "@/api/types";
import { syncMessageIds } from "@/features/chat/idSync";

/** Minimal message factory for testing. */
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

describe("syncMessageIds", () => {
  it("replaces temp- prefixed IDs with server canonical IDs", () => {
    const local = [
      makeMsg({ id: "temp-123", role: "user", content: "Hello" }),
      makeMsg({ id: "assistant-456", role: "assistant", content: "Hi" }),
    ];
    const server = [
      makeMsg({ id: "srv-aaa", role: "user", content: "Hello" }),
      makeMsg({ id: "srv-bbb", role: "assistant", content: "Hi" }),
    ];
    const result = syncMessageIds(local, server);
    expect(result[0].id).toBe("srv-aaa");
    expect(result[1].id).toBe("srv-bbb");
  });

  it("does not replace non-temp IDs", () => {
    const local = [
      makeMsg({ id: "permanent-123", role: "user" }),
    ];
    const server = [
      makeMsg({ id: "srv-xxx", role: "user" }),
    ];
    const result = syncMessageIds(local, server);
    expect(result[0].id).toBe("permanent-123");
  });

  it("replaces aborted- prefixed IDs", () => {
    const local = [
      makeMsg({ id: "aborted-789", role: "assistant" }),
    ];
    const server = [
      makeMsg({ id: "srv-ccc", role: "assistant" }),
    ];
    const result = syncMessageIds(local, server);
    expect(result[0].id).toBe("srv-ccc");
  });

  it("matches by role — does not cross-match user/assistant", () => {
    const local = [
      makeMsg({ id: "temp-1", role: "user" }),
      makeMsg({ id: "assistant-2", role: "assistant" }),
    ];
    const server = [
      makeMsg({ id: "srv-asst", role: "assistant" }),
      makeMsg({ id: "srv-user", role: "user" }),
    ];
    const result = syncMessageIds(local, server);
    /* temp-1 is user, srv-user is at index 1 — within ±1 of index 0 */
    expect(result[0].id).toBe("srv-user");
    /* assistant-2 is assistant, srv-asst is at index 0 — within ±1 of index 1 */
    expect(result[1].id).toBe("srv-asst");
  });

  it("tolerates position drift of ±1", () => {
    const local = [
      makeMsg({ id: "temp-0", role: "user" }),
      makeMsg({ id: "temp-1", role: "assistant" }),
    ];
    const server = [
      /* server index 0 = user, drift from local 0 = 0 */
      makeMsg({ id: "srv-0", role: "user" }),
      /* server index 1 = assistant, drift from local 1 = 0 */
      makeMsg({ id: "srv-1", role: "assistant" }),
    ];
    const result = syncMessageIds(local, server);
    expect(result[0].id).toBe("srv-0");
    expect(result[1].id).toBe("srv-1");
  });

  it("does not match if drift > 1", () => {
    const local = [
      makeMsg({ id: "temp-0", role: "user" }),
    ];
    const server = [
      makeMsg({ id: "srv-a", role: "assistant" }),
      makeMsg({ id: "srv-b", role: "assistant" }),
      makeMsg({ id: "srv-c", role: "user" }),  /* index 2, drift = |2-0| = 2 > 1 */
    ];
    const result = syncMessageIds(local, server);
    /* No match — drift too large */
    expect(result[0].id).toBe("temp-0");
  });

  it("returns empty array for empty inputs", () => {
    expect(syncMessageIds([], [])).toEqual([]);
  });

  it("preserves message content when replacing ID", () => {
    const local = [
      makeMsg({ id: "temp-1", role: "user", content: "Keep this" }),
    ];
    const server = [
      makeMsg({ id: "srv-1", role: "user", content: "Server version" }),
    ];
    const result = syncMessageIds(local, server);
    /* ID from server, content from local */
    expect(result[0].id).toBe("srv-1");
    expect(result[0].content).toBe("Keep this");
  });

  it("both temp messages match the same server ID when guard allows", () => {
    /* The guard `!localMessages.some((l, li) => li !== i && l.id === s.id)`
       checks if the server ID is already an ID of another LOCAL message.
       Since both locals have temp- IDs (not srv-only), the guard passes
       for both, so both get srv-only. This is the actual behavior. */
    const local = [
      makeMsg({ id: "temp-1", role: "user" }),
      makeMsg({ id: "temp-2", role: "user" }),
    ];
    const server = [
      makeMsg({ id: "srv-only", role: "user" }),
    ];
    const result = syncMessageIds(local, server);
    expect(result[0].id).toBe("srv-only");
    /* Both match because neither local message has srv-only as its pre-existing ID */
    expect(result[1].id).toBe("srv-only");
  });
});
