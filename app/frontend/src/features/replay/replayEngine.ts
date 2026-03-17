/**
 * Replay engine — drives pre-recorded session playback through the chat store.
 *
 * Module role:
 *   Iterates through a ReplayStep[] script, feeding events into
 *   chatStore.handleDelegationEvent() with timing delays that simulate
 *   real streaming. Uses the replayStore for lifecycle and the agentStore
 *   for tab switching during delegation.
 *
 * Architecture:
 *   The engine is a plain async function (not a React hook). It's called
 *   once from the WelcomeOverlay "Watch the Demo" button handler and
 *   runs to completion (or until aborted via the replayStore's AbortController).
 *
 * Key collaborators:
 *   - stores/replayStore.ts   — lifecycle (start/stop/abort, speed multiplier)
 *   - stores/chatStore.ts     — handleDelegationEvent() injects streaming events
 *   - stores/agentStore.ts    — viewDelegatedTab() for tab switching
 *   - features/replay/data/   — pre-recorded ReplayStep[] scripts
 */

import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useReplayStore } from "@/stores/replayStore";
import type { Message, ContentPart } from "@/api/types";
import { getScenarioDetail } from "@/api/scenarioApi";
import { convertSavedConversation } from "./data/convertSavedConversation";

export { convertSavedConversation } from "./data/convertSavedConversation";
export type { ConversionResult } from "./data/convertSavedConversation";

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Sleep that respects speed multiplier and abort signal. */
function sleep(ms: number, signal: AbortSignal): Promise<void> {
  const speed = useReplayStore.getState().speedMultiplier;
  const adjusted = Math.max(ms / speed, 5); // minimum 5ms to avoid starvation
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const timer = setTimeout(resolve, adjusted);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

function throwIfAborted(signal: AbortSignal) {
  if (signal.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }
}

/** Inject a synthetic user message into an agent's chat slice. */
function injectUserMessage(agentId: string, content: string) {
  const msg: Message = {
    id: `replay-user-${Date.now()}`,
    role: "user",
    content,
    parts: [{ type: "text", text: content } as ContentPart],
    status: "complete",
    tool_calls: [],
    agent_name: agentId,
    created_at: new Date().toISOString(),
  };
  const slice = useChatStore.getState().getSlice(agentId);
  useChatStore.setState((state) => ({
    slices: {
      ...state.slices,
      [agentId]: {
        ...slice,
        messages: [...slice.messages, msg],
      },
    },
  }));
}

// ── Main engine ─────────────────────────────────────────────────────────────

/**
 * Run the full replay sequence.
 *
 * Call this once from the UI entry point. It:
 *   1. Fetches the saved conversation JSON and converts to ReplayStep[]
 *   2. Clears all chat state
 *   3. Injects the user prompt into the orchestrator
 *   4. Iterates through each ReplayStep, feeding events with delays
 *   5. Pauses for the tour the first time each agent is seen
 *   6. Marks replay as done when complete (or off if aborted)
 */
export async function runReplay(): Promise<void> {
  const replayStore = useReplayStore.getState();
  const signal = replayStore._abortController?.signal;

  if (!signal) {
    console.warn("[replayEngine] No abort controller — was startReplay() called?");
    return;
  }

  try {
    // 1. Load scenario-local replay metadata first so the active scenario
    //    controls both the conversation payload and the detailed highlights.
    const scenario = await getScenarioDetail();
    const replayConversationUrl = scenario.replay_conversation_url || "/replay-conversation.json";

    // 2. Load the saved conversation and convert to replay steps
    const res = await fetch(replayConversationUrl);
    if (!res.ok) throw new Error(`Failed to load replay conversation: ${res.status}`);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const conversation = await res.json() as any;
    const { steps, userPrompt } = convertSavedConversation(
      conversation,
      scenario.replay_highlights || {},
    );

    // 3. Clear all existing chat state
    useChatStore.getState().clearAll();
    await useReplayStore.getState().pauseForTour(0);
    throwIfAborted(signal);

    // 4. Inject the user prompt into the orchestrator as a user message
    await sleep(300, signal);
    injectUserMessage("orchestrator", userPrompt);
    useAgentStore.getState().setActiveAgent("orchestrator");
    await useReplayStore.getState().pauseForTour(1);
    throwIfAborted(signal);

    // 5. Walk through each step
    //    Tour pauses are driven dynamically:
    //      - tourIndex 0: before start (already fired above)
    //      - tourIndex 1: orchestrator user prompt (already fired above)
    //      - tourIndex 2+: first delegation_start per agent, in order encountered
    //      - final: after orchestrator's last step completes
    const seenAgents = new Set<string>();
    let nextTourIndex = 2; // 0 and 1 already used above

    for (let stepIndex = 0; stepIndex < steps.length; stepIndex += 1) {
      const step = steps[stepIndex];
      if (signal.aborted) break;

      // Tab switch
      if (step.switchTab) {
        useAgentStore.getState().setActiveAgent(step.agentId);
      }

      // Feed events
      for (const event of step.events) {
        if (signal.aborted) break;

        // Wait before dispatching
        if (event.delayMs > 0) {
          await sleep(event.delayMs, signal);
        }

        // Highlight events pause the replay with an in-context callout —
        // they are NOT dispatched to the chat store.
        if (event.eventType === "highlight") {
          const { targetId, title, body } = event.data as {
            targetId: string;
            title: string;
            body: string;
          };
          await useReplayStore.getState().showHighlight({ targetId, title, body });
          throwIfAborted(signal);
          continue;
        }

        // Dispatch to chat store
        useChatStore
          .getState()
          .handleDelegationEvent(step.agentId, event.eventType, event.data);

        // Pause the first time each agent receives a delegation_start
        if (
          event.eventType === "delegation_start" &&
          !seenAgents.has(step.agentId)
        ) {
          seenAgents.add(step.agentId);
          await useReplayStore.getState().pauseForTour(nextTourIndex);
          nextTourIndex += 1;
          throwIfAborted(signal);
        }
      }

      // Small pause between steps for visual clarity
      if (!signal.aborted) {
        await sleep(800, signal);
      }
    }

    // Final tour pauses after the orchestrator's summary is complete
    await useReplayStore.getState().pauseForTour(nextTourIndex);
    throwIfAborted(signal);
    await useReplayStore.getState().pauseForTour(nextTourIndex + 1);
    throwIfAborted(signal);

    // 6. Done
    useReplayStore.getState().stopReplay();
    // Switch back to orchestrator to show the final summary
    useAgentStore.getState().setActiveAgent("orchestrator");
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      console.log("[replayEngine] Replay aborted by user");
      // Reset states for any agents still streaming
      const slices = useChatStore.getState().slices;
      for (const [agentId, slice] of Object.entries(slices)) {
        if (slice.status === "streaming") {
          useChatStore.getState().handleDelegationEvent(agentId, "done", {});
        }
      }
    } else {
      console.error("[replayEngine] Unexpected error:", err);
    }
    // cancelReplay already sets mode to "off"
  }
}
