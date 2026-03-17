/**
 * @module ChatInput
 *
 * User message input — auto-resizing textarea with send and abort controls.
 *
 * Provides the text entry point for the chat panel. The textarea grows
 * vertically with content (capped at 200 px) and resets after submission.
 * Keyboard bindings: Enter submits, Shift+Enter inserts a newline.
 * During active streaming, the send button is replaced with a red abort
 * button that calls `chatStore.abort()` to cancel the SSE stream.
 *
 * Submission is optimistic — the textarea clears immediately and
 * `chatStore.sendMessage(sessionId, content)` fires asynchronously.
 *
 * @remarks
 * - No props — all state is consumed from Zustand stores.
 * - Disabled entirely when no `activeSessionId` is set.
 *
 * @collaborators
 *   - {@link useChatStore}     — status, sendMessage, abort (read/write)
 *   - {@link useSessionStore}  — activeSessionId (read)
 *
 * @dependents
 *   Rendered by {@link ChatPanel} at the bottom of the chat column.
 */

import { useCallback, useRef, useState, KeyboardEvent, FormEvent } from "react";
import { Send, Square, Settings2, PlusCircle } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useReplayStore } from "@/stores/replayStore";
import { useScenario } from "@/hooks/useScenario";
import { DemoFlowPicker } from "./DemoFlowPicker";
import { ChatSettings } from "./ChatSettings";
import { useTranslation } from "@/hooks/useTranslation";

export function ChatInput({ agentId }: { agentId: string }) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const slice = useChatStore((s) => s.getSlice(agentId));
  const sendMessage = useChatStore((s) => s.sendMessage);
  const abort = useChatStore((s) => s.abort);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const createSession = useSessionStore((s) => s.createSession);
  const { scenario } = useScenario();
  const [showSettings, setShowSettings] = useState(false);
  const replayMode = useReplayStore((s) => s.mode);
  const { t } = useTranslation();

  const isStreaming = slice.status === "streaming" || replayMode === "playing";
  const demoFlows = scenario?.demo_flows ?? [];

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();

      if (!activeSessionId || isStreaming) return;

      const content = textareaRef.current?.value.trim();
      if (!content) return;

      // Clear input immediately (optimistic)
      if (textareaRef.current) {
        textareaRef.current.value = "";
        textareaRef.current.style.height = "auto";
      }

      await sendMessage(activeSessionId, content, agentId);
    },
    [activeSessionId, isStreaming, sendMessage, agentId],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleInput = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const handleAbort = useCallback(() => {
    if (activeSessionId) {
      abort(activeSessionId, agentId);
    }
  }, [activeSessionId, abort, agentId]);

  /** Handle demo flow step selection — send the prompt as a message. */
  const handleDemoSelect = useCallback(
    async (prompt: string) => {
      if (!activeSessionId || isStreaming) return;
      await sendMessage(activeSessionId, prompt, agentId);
    },
    [activeSessionId, isStreaming, sendMessage, agentId]
  );

  if (!activeSessionId) {
    return (
      <div className="border-t border-border bg-neutral-bg1 px-4 py-4">
        <p className="text-center text-sm text-text-muted">
          {t("chat.selectOrCreate")}
        </p>
        {(replayMode === "playing" || replayMode === "done") && (
          <div className="mt-3 flex justify-center">
            <button
              onClick={() => createSession()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-brand/10 border border-brand/30 text-brand text-sm font-medium hover:bg-brand/20 transition-colors"
            >
              <PlusCircle className="h-4 w-4" />
              {t("chat.newChat")}
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-neutral-bg1 px-4 py-3"
    >
      <div className="mx-auto flex items-center gap-2 px-2">
        {/* Demo flow picker — opens upward next to the chat input */}
        {demoFlows.length > 0 && (
          <DemoFlowPicker
            flows={demoFlows}
            onSelect={handleDemoSelect}
            disabled={isStreaming}
          />
        )}

        {/* Textarea */}
        <div className={`flex-1 rounded-2xl border transition-colors ${
          isStreaming
            ? 'border-white/10 bg-neutral-bg3 opacity-60'
            : 'border-white/10 bg-neutral-bg2 focus-within:border-white/25'
        }`}>
          <textarea
            ref={textareaRef}
            onKeyDown={handleKeyDown}
            onInput={handleInput}
            placeholder={t("chat.placeholder")}
            rows={1}
            disabled={isStreaming}
            className="w-full resize-none rounded-2xl bg-transparent px-4 py-3 text-sm text-text-primary placeholder-text-muted outline-none disabled:opacity-50"
            aria-label={t("chat.chatInput")}
          />
        </div>

        {/* Send / Abort button */}
        {isStreaming ? (
          <button
            type="button"
            onClick={handleAbort}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-status-error/20 text-status-error hover:bg-status-error/30 transition-colors"
            aria-label={t("chat.stopGenerating")}
          >
            <Square className="h-4 w-4 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand text-white hover:bg-brand-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label={t("chat.sendMessage")}
          >
            <Send className="h-4 w-4" />
          </button>
        )}

        {/* Font size controls — positioned after the send button */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowSettings(!showSettings)}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-neutral-bg3 text-text-secondary hover:bg-neutral-bg4 hover:text-text-primary transition-colors"
            aria-label={t("chat.chatSettings")}
            title={t("chat.contextSettings")}
          >
            <Settings2 className="h-3.5 w-3.5" />
          </button>
          {showSettings && <ChatSettings onClose={() => setShowSettings(false)} />}
        </div>
      </div>
    </form>
  );
}
