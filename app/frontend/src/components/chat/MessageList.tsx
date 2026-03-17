/**
 * @module MessageList
 *
 * Scrollable message list — the vertical timeline of chat messages.
 *
 * Renders all persisted messages from `chatStore.messages` via
 * {@link MessageBubble}, plus an in-flight streaming bubble when
 * `status === 'streaming'`. Uses {@link useAutoScroll} for smart
 * auto-scroll behaviour: follows new content during streaming but
 * pauses when the user manually scrolls up, with a floating
 * "scroll to bottom" button to re-engage.
 *
 * Displays an empty state (icon + prompt text) when no session is
 * active or the conversation has no messages yet.
 *
 * @remarks
 * - No props — all state is consumed from `chatStore`.
 * - The streaming bubble is a synthetic {@link MessageBubble} with
 *   `isStreaming=true` and `streamingParts` from the store.
 *
 * @collaborators
 *   - {@link useChatStore}    — messages, status, streamingParts (read)
 *   - {@link useAutoScroll}   — containerRef, handleScroll, scrollToBottom
 *   - {@link MessageBubble}   — rendered child per message
 *
 * @dependents
 *   Rendered by {@link ChatPanel} as the scrollable body.
 */

import { ArrowDown, MessageSquare, PlusCircle, CornerUpLeft, Play } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useAgentStore } from "@/stores/agentStore";
import { useReplayStore } from "@/stores/replayStore";
import { runReplay } from "@/features/replay/replayEngine";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { useTranslation } from "@/hooks/useTranslation";
import { MessageBubble } from "./MessageBubble";

export function MessageList() {
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const messages = useChatStore((s) => s.getSlice(activeAgentId).messages);
  const status = useChatStore((s) => s.getSlice(activeAgentId).status);
  const streamingParts = useChatStore((s) => s.getSlice(activeAgentId).streamingParts);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const createSession = useSessionStore((s) => s.createSession);

  const { containerRef, handleScroll, scrollToBottom, showScrollButton } =
    useAutoScroll({
      threshold: 120,
      deps: [streamingParts.length, messages.length],
    });

  const returnToAgentId = useAgentStore((s) => s.returnToAgentId);
  const returnToOrigin = useAgentStore((s) => s.returnToOrigin);
  const { t } = useTranslation();

  // Empty state
  if (messages.length === 0 && status === "idle") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-text-muted">
        <MessageSquare className="h-12 w-12 opacity-30" />
        <div className="text-center">
          <p className="text-lg font-medium">
            {activeSessionId ? t('chat.startConversation') : t('chat.noSessionLoaded')}
          </p>
          <p className="text-sm mt-1">
            {activeSessionId
              ? t('chat.typeBelow')
              : t('chat.createSession')}
          </p>
        </div>
        {/* New Chat button — only shown when no session is active */}
        {!activeSessionId && (
          <div className="flex flex-col items-center gap-2 mt-2">
            <button
              onClick={() => createSession()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand/10 border border-brand/30 text-brand text-sm font-medium hover:bg-brand/20 transition-colors"
            >
              <PlusCircle className="h-4 w-4" />
              {t('chat.newChat')}
            </button>
            <button
              onClick={() => {
                useReplayStore.getState().startReplay();
                runReplay();
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-hover transition-colors"
            >
              <Play className="h-4 w-4 fill-current" />
              {t('chat.watchDemo')}
            </button>
          </div>
        )}
      </div>
    );
  }

  // Determine if the last message is the one being streamed
  const isStreaming = status === "streaming";

  return (
    <div className="relative flex-1 overflow-hidden">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto scroll-smooth"
      >
        <div className="mx-auto px-6 py-4">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
            />
          ))}

          {/* Streaming placeholder (assistant response in progress) */}
          {isStreaming && (
            <MessageBubble
              message={{
                id: "streaming",
                role: "assistant",
                content: "",
                parts: [],
                status: "streaming",
                tool_calls: [],
                agent_name: "",
                created_at: new Date().toISOString(),
              }}
              streamingParts={streamingParts}
              isStreaming
            />
          )}
        </div>
      </div>

      {/* New messages button — far right */}
      {showScrollButton && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 right-4 flex items-center gap-1.5 rounded-full bg-neutral-bg3 px-3 py-1.5 text-xs text-text-secondary shadow-lg border border-border hover:bg-neutral-bg4 transition-colors"
          aria-label={t('chat.scrollToBottom')}
        >
          <ArrowDown className="h-3.5 w-3.5" />
          <span>{t('chat.newMessages')}</span>
        </button>
      )}

      {/* Return to Origin button — bottom center, only after "View Tab" navigation */}
      {returnToAgentId && (
        <button
          onClick={returnToOrigin}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-neutral-bg3 px-3 py-1.5 text-xs text-text-secondary shadow-lg border border-border hover:bg-neutral-bg4 transition-colors"
          aria-label={t('chat.returnToOriginAria')}
        >
          <CornerUpLeft className="h-3.5 w-3.5" />
          <span>{t('chat.returnToOrigin')}</span>
        </button>
      )}
    </div>
  );
}
