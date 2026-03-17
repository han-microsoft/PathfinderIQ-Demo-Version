/**
 * Agent tab isolation tests — verifies per-agent chat slices are independent.
 *
 * Purpose:
 *   Ensures that each agent tab (orchestrator, investigator, etc.) has its own
 *   fully independent state: messages, streaming status, tool calls, errors,
 *   and timing. Operations on one agent's slice must NEVER affect another's.
 *
 * What this tests:
 *   1. getSlice() creates independent default slices per agent
 *   2. Messages added to one slice don't appear in another
 *   3. Error state in one slice doesn't bleed to others
 *   4. loadSessionMessages() populates each agent's slice from its thread only
 *   5. clearChat() clears only the targeted agent, leaves others intact
 *   6. clearAll() resets every slice
 *   7. Streaming state (status, streamingParts) is per-agent
 *
 * Architecture:
 *   The chatStore uses a `slices: Record<string, AgentChatSlice>` map.
 *   _getSlice(agentId) lazy-creates a default slice if missing.
 *   _setSlice/_updateSlice patch a single agent's slice without touching others.
 *
 * Dependents:
 *   Guards the correctness of: ChatPanel, AgentTabBar, MessageList, ChatInput
 */
import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "@/stores/chatStore";
import type { AgentThread, Message } from "@/api/types";

/* ── Helpers ── */

/** Build a minimal Message for testing. */
function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    role: "assistant",
    content: "test content",
    parts: [{ type: "text", text: "test content" }],
    status: "complete",
    tool_calls: [],
    agent_name: "orchestrator",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

/** Build a minimal AgentThread for loadSessionMessages. */
function makeThread(agentId: string, messages: Message[]): AgentThread {
  return {
    agent_session_id: `ast_${agentId}_123`,
    agent_id: agentId,
    agent_name: agentId,
    messages,
    created_at: new Date().toISOString(),
  };
}

describe("Agent Tab Isolation", () => {
  /* Reset all slices before each test to prevent inter-test bleed */
  beforeEach(() => {
    useChatStore.getState().clearAll();
  });

  // ── 1. Independent default slices ────────────────────────────────

  it("creates independent default slices for different agents", () => {
    const sliceA = useChatStore.getState().getSlice("orchestrator");
    const sliceB = useChatStore.getState().getSlice("investigator");

    /* Both start with default state */
    expect(sliceA.messages).toEqual([]);
    expect(sliceB.messages).toEqual([]);
    expect(sliceA.status).toBe("idle");
    expect(sliceB.status).toBe("idle");

    /* They are not the same object reference */
    expect(sliceA).not.toBe(sliceB);
  });

  it("getSlice is idempotent — returns same data on repeated calls", () => {
    const first = useChatStore.getState().getSlice("orchestrator");
    const second = useChatStore.getState().getSlice("orchestrator");
    expect(first.messages).toEqual(second.messages);
    expect(first.status).toBe(second.status);
  });

  // ── 2. Message isolation ─────────────────────────────────────────

  it("messages added to one agent do NOT appear in another", () => {
    const msg = makeMsg({ agent_name: "orchestrator" });

    /* Manually set messages on orchestrator slice */
    useChatStore.setState((state) => ({
      slices: {
        ...state.slices,
        orchestrator: {
          ...useChatStore.getState().getSlice("orchestrator"),
          messages: [msg],
        },
      },
    }));

    /* Orchestrator has the message */
    const orchSlice = useChatStore.getState().getSlice("orchestrator");
    expect(orchSlice.messages).toHaveLength(1);
    expect(orchSlice.messages[0].content).toBe("test content");

    /* Investigator has NO messages */
    const invSlice = useChatStore.getState().getSlice("investigator");
    expect(invSlice.messages).toHaveLength(0);
  });

  it("multiple agents can have different message counts simultaneously", () => {
    const threads: Record<string, AgentThread> = {
      orchestrator: makeThread("orchestrator", [
        makeMsg({ role: "system", content: "sys prompt" }),
        makeMsg({ role: "user", content: "Q1" }),
        makeMsg({ role: "assistant", content: "A1" }),
      ]),
      investigator: makeThread("investigator", [
        makeMsg({ role: "system", content: "sys prompt 2" }),
        makeMsg({ role: "user", content: "Q2" }),
      ]),
      analyst: makeThread("analyst", [
        makeMsg({ role: "system", content: "sys prompt 3" }),
      ]),
    };

    useChatStore.getState().loadSessionMessages(threads, "orchestrator");

    /* System messages are filtered out — only user/assistant messages remain */
    expect(useChatStore.getState().getSlice("orchestrator").messages).toHaveLength(2);
    expect(useChatStore.getState().getSlice("investigator").messages).toHaveLength(1);
    /* Analyst has only a system message → filtered out → 0 display messages */
    expect(useChatStore.getState().getSlice("analyst").messages).toHaveLength(0);
  });

  // ── 3. Error state isolation ─────────────────────────────────────

  it("error in one agent does not affect other agents", () => {
    /* Set error on orchestrator */
    useChatStore.setState((state) => ({
      slices: {
        ...state.slices,
        orchestrator: {
          ...useChatStore.getState().getSlice("orchestrator"),
          status: "error" as const,
          error: "Rate limited",
        },
      },
    }));

    /* Orchestrator has error */
    expect(useChatStore.getState().getSlice("orchestrator").error).toBe("Rate limited");
    expect(useChatStore.getState().getSlice("orchestrator").status).toBe("error");

    /* Investigator is unaffected */
    expect(useChatStore.getState().getSlice("investigator").error).toBeNull();
    expect(useChatStore.getState().getSlice("investigator").status).toBe("idle");
  });

  // ── 4. loadSessionMessages isolation ─────────────────────────────

  it("loadSessionMessages populates each agent from its own thread only", () => {
    const orchMsg = makeMsg({ role: "user", content: "Ask about routers" });
    const invMsg = makeMsg({ role: "user", content: "Check telemetry" });

    const threads: Record<string, AgentThread> = {
      orchestrator: makeThread("orchestrator", [
        makeMsg({ role: "system", content: "You are the orchestrator" }),
        orchMsg,
      ]),
      investigator: makeThread("investigator", [
        makeMsg({ role: "system", content: "You are the investigator" }),
        invMsg,
      ]),
    };

    useChatStore.getState().loadSessionMessages(threads, "orchestrator");

    const orchSlice = useChatStore.getState().getSlice("orchestrator");
    const invSlice = useChatStore.getState().getSlice("investigator");

    /* Each agent gets only its own messages */
    expect(orchSlice.messages).toHaveLength(1); /* system filtered out */
    expect(orchSlice.messages[0].content).toBe("Ask about routers");

    expect(invSlice.messages).toHaveLength(1);
    expect(invSlice.messages[0].content).toBe("Check telemetry");

    /* No cross-contamination — orchestrator messages NOT in investigator */
    expect(invSlice.messages.some((m) => m.content === "Ask about routers")).toBe(false);
  });

  it("loadSessionMessages filters system messages from display", () => {
    const threads: Record<string, AgentThread> = {
      orchestrator: makeThread("orchestrator", [
        makeMsg({ role: "system", content: "System prompt text" }),
        makeMsg({ role: "user", content: "Hello" }),
        makeMsg({ role: "assistant", content: "Hi there" }),
      ]),
    };

    useChatStore.getState().loadSessionMessages(threads, "orchestrator");

    const slice = useChatStore.getState().getSlice("orchestrator");
    expect(slice.messages).toHaveLength(2);
    expect(slice.messages.every((m) => m.role !== "system")).toBe(true);
  });

  // ── 5. clearChat targets only one agent ──────────────────────────

  it("clearChat(agentId) resets only that agent, others untouched", () => {
    /* Load messages into two agents */
    const threads: Record<string, AgentThread> = {
      orchestrator: makeThread("orchestrator", [
        makeMsg({ role: "user", content: "Orch msg" }),
      ]),
      investigator: makeThread("investigator", [
        makeMsg({ role: "user", content: "Inv msg" }),
      ]),
    };
    useChatStore.getState().loadSessionMessages(threads, "orchestrator");

    /* Clear only orchestrator */
    useChatStore.getState().clearChat("orchestrator");

    /* Orchestrator is reset */
    expect(useChatStore.getState().getSlice("orchestrator").messages).toHaveLength(0);
    expect(useChatStore.getState().getSlice("orchestrator").status).toBe("idle");

    /* Investigator is untouched */
    expect(useChatStore.getState().getSlice("investigator").messages).toHaveLength(1);
    expect(useChatStore.getState().getSlice("investigator").messages[0].content).toBe("Inv msg");
  });

  // ── 6. clearAll resets every agent ───────────────────────────────

  it("clearAll() wipes all agent slices", () => {
    const threads: Record<string, AgentThread> = {
      orchestrator: makeThread("orchestrator", [
        makeMsg({ role: "user", content: "O" }),
      ]),
      investigator: makeThread("investigator", [
        makeMsg({ role: "user", content: "I" }),
      ]),
      analyst: makeThread("analyst", [
        makeMsg({ role: "user", content: "A" }),
      ]),
    };
    useChatStore.getState().loadSessionMessages(threads, "orchestrator");

    useChatStore.getState().clearAll();

    /* All slices are empty after clearAll */
    expect(useChatStore.getState().getSlice("orchestrator").messages).toHaveLength(0);
    expect(useChatStore.getState().getSlice("investigator").messages).toHaveLength(0);
    expect(useChatStore.getState().getSlice("analyst").messages).toHaveLength(0);
  });

  // ── 7. Streaming state isolation ─────────────────────────────────

  it("streaming status on one agent does not affect others", () => {
    useChatStore.setState((state) => ({
      slices: {
        ...state.slices,
        orchestrator: {
          ...useChatStore.getState().getSlice("orchestrator"),
          status: "streaming" as const,
          streamingParts: [{ type: "text" as const, text: "thinking..." }],
        },
      },
    }));

    expect(useChatStore.getState().getSlice("orchestrator").status).toBe("streaming");
    expect(useChatStore.getState().getSlice("orchestrator").streamingParts).toHaveLength(1);

    /* Other agents remain idle with no streaming parts */
    expect(useChatStore.getState().getSlice("investigator").status).toBe("idle");
    expect(useChatStore.getState().getSlice("investigator").streamingParts).toHaveLength(0);
  });

  it("rateLimitCountdown is per-agent", () => {
    useChatStore.setState((state) => ({
      slices: {
        ...state.slices,
        orchestrator: {
          ...useChatStore.getState().getSlice("orchestrator"),
          rateLimitCountdown: 30,
        },
      },
    }));

    expect(useChatStore.getState().getSlice("orchestrator").rateLimitCountdown).toBe(30);
    expect(useChatStore.getState().getSlice("investigator").rateLimitCountdown).toBeNull();
  });

  it("TTFT/TTLT tracking is per-agent", () => {
    useChatStore.setState((state) => ({
      slices: {
        ...state.slices,
        orchestrator: {
          ...useChatStore.getState().getSlice("orchestrator"),
          ttftMs: 150,
          ttltMs: 3000,
          ttftHistory: [100, 150],
          ttltHistory: [2500, 3000],
        },
      },
    }));

    const orch = useChatStore.getState().getSlice("orchestrator");
    expect(orch.ttftMs).toBe(150);
    expect(orch.ttltHistory).toEqual([2500, 3000]);

    const inv = useChatStore.getState().getSlice("investigator");
    expect(inv.ttftMs).toBeNull();
    expect(inv.ttltHistory).toEqual([]);
  });
});
