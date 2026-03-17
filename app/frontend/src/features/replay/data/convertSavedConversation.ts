/**
 * Convert a saved conversation JSON (schema v3) into a ReplayStep[] script.
 *
 * Module role:
 *   Reads the server-persisted conversation structure (threads keyed by
 *   agent_id, messages with tool_calls) and produces the ordered sequence
 *   of ReplayEvent[] that the replay engine feeds into chatStore.handleDelegationEvent().
 *
 * Architecture:
 *   The converter walks the orchestrator's assistant message tool_calls in order.
 *   For each tool_call:
 *     - If it's a `delegate_to_agent`, it looks up the target agent's thread,
 *       reconstructs that agent's tool calls and response text as a separate
 *       ReplayStep, and records the delegation tool_call_start/end on the
 *       orchestrator step.
 *     - If it's `thinking`, it emits a thinking event on the current orchestrator step.
 *     - Otherwise (reroute_traffic, set_link_status, etc.) it emits tool_call events
 *       on the orchestrator's post-delegation step.
 *   The orchestrator's final content text is emitted as streamed tokens at the end.
 *
 * Key collaborators:
 *   - features/replay/types.ts    — ReplayStep, ReplayEvent shapes
 *   - features/replay/replayEngine.ts — consumes the output
 *   - stores/chatStore.ts         — handleDelegationEvent() processes the events
 *
 * Usage:
 *   import { convertSavedConversation } from "./convertSavedConversation";
 *   const { steps, userPrompt } = convertSavedConversation(jsonData);
 */

import type { ReplayStep, ReplayEvent } from "../types";

export interface ReplayHighlightEntry {
  title: string;
  body: string;
}

// ── Types for the saved conversation JSON structure ─────────────────────────

/** A single tool call as persisted in the saved conversation JSON. */
interface SavedToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string | null;
  duration_ms?: number | null;
}

/** A single message within a thread. */
interface SavedMessage {
  id: string;
  role: "system" | "user" | "assistant";
  content: string;
  status: string;
  tool_calls: SavedToolCall[];
  agent_name: string;
  created_at: string;
}

/** A per-agent thread. */
interface SavedThread {
  agent_id: string;
  agent_name: string;
  messages: SavedMessage[];
}

/** Top-level saved conversation structure. */
interface SavedConversation {
  id: string;
  threads: Record<string, SavedThread>;
  [key: string]: unknown;
}

/** Result of the conversion — steps for the engine plus the user prompt text. */
export interface ConversionResult {
  steps: ReplayStep[];
  userPrompt: string;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Break text into word-boundary chunks to simulate token streaming. */
function tokenize(text: string, chunkSize = 3): string[] {
  const words = text.split(/(\s+)/);
  const chunks: string[] = [];
  let buf = "";
  for (const w of words) {
    buf += w;
    if (buf.split(/\s+/).filter(Boolean).length >= chunkSize) {
      chunks.push(buf);
      buf = "";
    }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

/** Create token events with inter-token delays. */
function textTokens(text: string, tokenDelay = 40, chunkSize = 3): ReplayEvent[] {
  return tokenize(text, chunkSize).map((chunk) => ({
    delayMs: tokenDelay,
    eventType: "token",
    data: { token: chunk },
  }));
}

/**
 * Compute a plausible tool result display delay from the saved duration_ms.
 * Caps between 200ms and 3000ms to keep the replay watchable.
 */
function toolResultDelay(durationMs: number | null | undefined): number {
  if (!durationMs || durationMs <= 0) return 1200;
  /* Scale real duration down: use log-scale so multi-minute operations
     don't stall the replay. */
  const scaled = Math.min(4000, Math.max(400, Math.log10(durationMs) * 600));
  return Math.round(scaled);
}

// ── Core conversion logic ───────────────────────────────────────────────────

/**
 * Build a ReplayStep for a delegated agent using its thread data.
 *
 * Walks the agent's assistant message (the last one), extracting:
 *   - tool_calls → tool_call_start / tool_call_end / tool_result events
 *   - thinking tool_calls → thinking events
 *   - assistant content → streamed token events
 *
 * @param thread      — the agent's thread from the saved conversation
 * @param highlights  — tool_call ID → highlight callout to inject after that tool result
 * @returns a ReplayStep targeting that agent
 */
function buildDelegatedAgentStep(
  thread: SavedThread,
  highlights: Record<string, { title: string; body: string }>,
): ReplayStep {
  const events: ReplayEvent[] = [];

  /* Start the delegation stream on this agent's tab. */
  events.push({ delayMs: 800, eventType: "delegation_start", data: {} });

  /* Find the assistant message — it's the response to the delegated task. */
  const assistantMsg = thread.messages.find((m) => m.role === "assistant");
  if (!assistantMsg) {
    /* No assistant response — agent may have failed. Emit error + done. */
    events.push({ delayMs: 500, eventType: "error", data: { error: "Agent did not respond" } });
    return { agentId: thread.agent_id, switchTab: true, events };
  }

  /* Walk the tool_calls in order. Each is either a thinking call,
     a graph/alert/telemetry query, or a runbook/ticket/equipment search. */
  for (const tc of assistantMsg.tool_calls) {
    if (tc.name === "thinking") {
      /* Emit a thinking block with the thought text. */
      const thought = (tc.arguments?.thoughts as string) || "";
      if (thought) {
        events.push({ delayMs: 400, eventType: "thinking", data: { token: "" } });
        events.push(...textTokens(thought, 35, 4));
      }
    } else {
      /* Standard tool call: start → end (with args) → result. */
      events.push({
        delayMs: 400,
        eventType: "tool_call_start",
        data: { id: tc.id, name: tc.name },
      });
      events.push({
        delayMs: 300,
        eventType: "tool_call_end",
        data: { id: tc.id, arguments: tc.arguments },
      });

      /* Emit the tool result if present. */
      if (tc.result != null) {
        events.push({
          delayMs: toolResultDelay(tc.duration_ms),
          eventType: "tool_result",
          data: {
            id: tc.id,
            name: tc.name,
            result: typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result),
          },
        });
      }

      /* Inject highlight if annotated — fires after tool result is rendered. */
      if (highlights[tc.id]) {
        const hl = highlights[tc.id];
        events.push({
          delayMs: 600,
          eventType: "highlight",
          data: { targetId: tc.id, title: hl.title, body: hl.body },
        });
      }
    }
  }

  /* Stream the assistant's response content as tokens. */
  if (assistantMsg.content) {
    events.push(...textTokens(assistantMsg.content, 20, 4));
  }

  /* Close the stream. */
  events.push({ delayMs: 400, eventType: "done", data: {} });

  return { agentId: thread.agent_id, switchTab: true, events };
}

/**
 * Convert a saved conversation JSON into ReplayStep[] + userPrompt.
 *
 * @param conversation — the parsed saved conversation object
 * @param highlights — tool-call keyed highlight annotations for detailed replay
 * @returns steps for the replay engine and the user prompt text
 */
export function convertSavedConversation(
  conversation: SavedConversation,
  highlights: Record<string, ReplayHighlightEntry> = {},
): ConversionResult {
  const threads = conversation.threads;
  const orchThread = threads["orchestrator"];
  if (!orchThread) {
    throw new Error("Saved conversation has no orchestrator thread");
  }

  /* Extract the user prompt (the first user message in the orchestrator thread). */
  const userMsg = orchThread.messages.find((m) => m.role === "user");
  const userPrompt = userMsg?.content || "";

  /* Find the orchestrator's assistant message — contains the full tool_call sequence. */
  const orchAssistant = orchThread.messages.find((m) => m.role === "assistant");
  if (!orchAssistant) {
    throw new Error("Saved conversation has no orchestrator assistant message");
  }

  const steps: ReplayStep[] = [];
  const orchToolCalls = orchAssistant.tool_calls;

  /* Walk orchestrator tool_calls sequentially. Accumulate events for the
     current orchestrator segment. When a delegate_to_agent is encountered:
       1. Emit the delegation tool_call_start/end into the current segment
       2. Flush the current segment as an orchestrator ReplayStep
       3. Emit the delegated agent's ReplayStep (from its thread)
       4. Start a new orchestrator segment with the delegation tool_result
     This preserves the interleaved execution order:
       orch(plan) → agent1 → agent2 → orch(remediate) → agent4 → orch(summary) */

  let currentOrchestratorEvents: ReplayEvent[] = [];
  let isFirstOrchestratorStep = true;

  /** Flush accumulated orchestrator events as a ReplayStep (if non-empty). */
  function flushOrchestratorStep() {
    if (currentOrchestratorEvents.length === 0) return;

    const events: ReplayEvent[] = [];
    /* The first orchestrator step needs a delegation_start to begin streaming. */
    if (isFirstOrchestratorStep) {
      events.push({ delayMs: 800, eventType: "delegation_start", data: {} });
      isFirstOrchestratorStep = false;
    }
    events.push(...currentOrchestratorEvents);

    steps.push({ agentId: "orchestrator", switchTab: true, events });
    currentOrchestratorEvents = [];
  }

  for (const tc of orchToolCalls) {
    if (tc.name === "thinking") {
      /* Accumulate thinking events into the current orchestrator segment. */
      const thought = (tc.arguments?.thoughts as string) || "";
      if (!thought) continue;
      currentOrchestratorEvents.push(
        { delayMs: 400, eventType: "thinking", data: { token: "" } },
        ...textTokens(thought, 35, 4),
      );
    } else if (tc.name === "delegate_to_agent") {
      const targetAgentId = tc.arguments?.agent_id as string;

      /* Emit the delegation tool_call on the current orchestrator segment. */
      currentOrchestratorEvents.push({
        delayMs: 500,
        eventType: "tool_call_start",
        data: { id: tc.id, name: "delegate_to_agent" },
      });
      currentOrchestratorEvents.push({
        delayMs: 400,
        eventType: "tool_call_end",
        data: { id: tc.id, arguments: tc.arguments },
      });

      /* Inject highlight if annotated — fires while the tool card is visible. */
      if (highlights[tc.id]) {
        const hl = highlights[tc.id];
        currentOrchestratorEvents.push({
          delayMs: 600,
          eventType: "highlight",
          data: { targetId: tc.id, title: hl.title, body: hl.body },
        });
      }

      /* Flush the orchestrator segment before switching to the agent tab. */
      flushOrchestratorStep();

      /* Build the delegated agent's step from its thread. */
      const agentThread = threads[targetAgentId];
      if (agentThread) {
        steps.push(buildDelegatedAgentStep(agentThread, highlights));
      }

      /* Start next orchestrator segment with the delegation tool_result. */
      const resultStr = tc.result != null
        ? (typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result))
        : JSON.stringify({ agent_id: targetAgentId, status: "complete" });

      currentOrchestratorEvents.push({
        delayMs: 400,
        eventType: "tool_result",
        data: { id: tc.id, name: "delegate_to_agent", result: resultStr },
      });
    } else {
      /* Non-thinking, non-delegation tool call (reroute, dispatch, etc.). */
      currentOrchestratorEvents.push({
        delayMs: 500,
        eventType: "tool_call_start",
        data: { id: tc.id, name: tc.name },
      });
      currentOrchestratorEvents.push({
        delayMs: 400,
        eventType: "tool_call_end",
        data: { id: tc.id, arguments: tc.arguments },
      });

      if (tc.result != null) {
        currentOrchestratorEvents.push({
          delayMs: toolResultDelay(tc.duration_ms),
          eventType: "tool_result",
          data: {
            id: tc.id,
            name: tc.name,
            result: typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result),
          },
        });
      }

      /* Inject highlight if annotated — fires after tool result is rendered. */
      if (highlights[tc.id]) {
        const hl = highlights[tc.id];
        currentOrchestratorEvents.push({
          delayMs: 600,
          eventType: "highlight",
          data: { targetId: tc.id, title: hl.title, body: hl.body },
        });
      }
    }
  }

  /* Append the orchestrator's final content as streamed tokens. */
  if (orchAssistant.content) {
    currentOrchestratorEvents.push(...textTokens(orchAssistant.content, 40, 3));
  }

  /* Close the orchestrator stream. */
  currentOrchestratorEvents.push({ delayMs: 400, eventType: "done", data: {} });

  /* Flush the final orchestrator segment. */
  flushOrchestratorStep();

  return { steps, userPrompt };
}
