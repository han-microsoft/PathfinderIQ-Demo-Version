/**
 * @module ChatPanel
 *
 * Main chat container — the primary conversational interface for the
 * scenario-driven AI agent application.
 *
 * Composes MessageList (scrollable message history) and ChatInput
 * (user textarea + send/abort controls) into a single vertical flex
 * column. Surfaces an error banner when chatStore.error is set,
 * and a metadata bar (model name, token count, latency) after each
 * completed assistant turn.
 *
 * @remarks
 * - No props — all state is consumed from Zustand stores.
 * - The metadata bar reads `lastMetadata` from chatStore, which is
 *   populated by the SSE stream's final `[DONE]` event.
 *
 * @collaborators
 *   - {@link useChatStore}     — error, lastMetadata (read)
 *   - {@link useSessionStore}  — activeSessionId (read)
 *   - {@link MessageList}      — rendered child (message history)
 *   - {@link ChatInput}        — rendered child (user input)
 *
 * @dependents
 *   Rendered by the root App layout as the right-hand panel.
 */

import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AgentTabBar } from "./AgentTabBar";
import { useSessionEvents } from "@/hooks/useSessionEvents";

export function ChatPanel() {
  const activeAgentId = useAgentStore((s) => s.activeAgentId);
  const agentId = activeAgentId ?? "orchestrator";
  const error = useChatStore((s) => s.getSlice(agentId).error);
  const errorCode = useChatStore((s) => s.getSlice(agentId).errorCode);

  /* Subscribe to the per-session delegation event bus.
     Events from specialist agents stream into their respective tabs. */
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  useSessionEvents(activeSessionId);

  return (
    <main className="flex flex-1 flex-col bg-neutral-bg1 overflow-hidden">
      {/* Agent tab bar */}
      <AgentTabBar />

      {/* Error banner */}
      {error && (
        <div className="border-b border-status-error/30 bg-status-error/10 px-4 py-2 text-sm text-status-error">
          {error}
          {errorCode && <span className="text-xs opacity-60 ml-2">[{errorCode}]</span>}
        </div>
      )}

      {/* Messages */}
      <MessageList />

      {/* Input */}
      <ChatInput agentId={agentId} />
    </main>
  );
}
