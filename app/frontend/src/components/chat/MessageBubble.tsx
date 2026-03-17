/**
 * @module MessageBubble
 *
 * Single message renderer — displays one user or assistant message
 * within the conversation timeline.
 *
 * User messages render as plain text in a right-aligned bubble.
 * Assistant messages render an ordered array of {@link ContentPart}
 * objects, each dispatched to its specialised sub-component:
 *   - {@link ThinkingBlock}   — intermediate reasoning (💭 muted italic)
 *   - {@link ToolCallDisplay} — collapsible tool invocation card
 *   - {@link TextBlock}       — markdown-rendered final text
 *
 * Parts are rendered in chronological order exactly as they arrived
 * from the SSE stream, preserving the interleaved thinking → tool →
 * text flow. For legacy messages that lack a `parts` array,
 * `legacyToParts()` from `partUtils.ts` synthesises one from
 * `tool_calls` + `content`.
 *
 * During active streaming, `streamingParts` are rendered instead of
 * persisted parts, and a {@link StreamingIndicator} is appended.
 *
 * @props
 *   - `message`        — the {@link Message} object (id, role, content, parts, status)
 *   - `streamingParts`  — live parts array during SSE generation (optional)
 *   - `isStreaming`     — whether this bubble represents the in-flight response
 *
 * @collaborators
 *   - {@link ToolCallDisplay}   — renders tool_call parts
 *   - {@link ThinkingBlock}     — renders thinking parts
 *   - {@link TextBlock}         — renders text parts
 *   - {@link StreamingIndicator} — typing dots during streaming
 *
 * @dependents
 *   Rendered by {@link MessageList} for each message in the conversation.
 */

import { useState, memo } from "react";
import { User, AlertCircle, StopCircle, ChevronRight } from "lucide-react";
import type { Message, ContentPart } from "@/api/types";
import { useChatSettingsStore } from "@/stores/chatSettingsStore";
import { useAgentStore } from "@/stores/agentStore";
import { getAgentHeadshot } from "@/utils/agentHeadshots";
import { legacyToParts } from "@/features/chat/partUtils";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";
import { ToolCallDisplay } from "./ToolCallDisplay";
import { ThinkingBlock } from "./ThinkingBlock";
import { TextBlock } from "./TextBlock";
import { StreamingIndicator } from "./StreamingIndicator";
import { useTranslation } from "@/hooks/useTranslation";

interface MessageBubbleProps {
  message: Message;
  /** Streaming parts (only for the current assistant message). */
  streamingParts?: ContentPart[];
  isStreaming?: boolean;
}

export const MessageBubble = memo(function MessageBubble({
  message,
  streamingParts,
  isStreaming = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  const isAborted = message.status === "aborted";

  /* Collapsible state — expanded by default, click to collapse to one line */
  const [collapsed, setCollapsed] = useState(false);
  const { t } = useTranslation();

  /* Font size from user preference store */
  const chatTextScale = useChatSettingsStore((s) => s.chatTextScale);
  const fontSize = `${Math.round(14 * chatTextScale / 100)}px`;

  /* Delegation label — show the delegating agent's name above the user icon
     when this user message was delegated from another agent (e.g., orchestrator
     sends a task to networkInvestigator). Detected by: user message whose
     agent_name differs from the current tab's agent. */
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const agents = useAgentStore((s) => s.agents);
  const activeAgent = agents.find((a) => a.id === activeAgentId);
  const agentHeadshot = activeAgent?.headshot_url
    ?? getAgentHeadshot(activeAgent?.name ?? activeAgentId);
  const delegatedFrom = isUser && message.agent_name && message.agent_name !== activeAgentId
    ? message.agent_name
    : null;

  // Determine parts to render — filter out any undefined/null entries
  // that can occur when SSE events arrive with malformed or truncated data.
  const parts: ContentPart[] = (isStreaming
    ? (streamingParts ?? [])
    : (message.parts?.length ? message.parts : legacyToParts(message))
  ).filter((p): p is ContentPart => p != null && typeof p === "object" && "type" in p);

  const timestamp = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  /** Toggle collapsed state — used by avatar, chevron, and timestamp. */
  const toggleCollapse = (e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsed((v) => !v);
  };

  return (
    <article
      className={`flex gap-3 px-4 py-3 group/msg ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
      aria-label={`${message.role} message at ${timestamp}`}
    >
      {/* Avatar column — optional delegation label above the icon */}
      <div className={`flex flex-col items-center shrink-0 gap-0.5 ${isUser ? "order-last" : ""}`}>
        {/* Delegation label — shows which agent delegated this task */}
        {delegatedFrom && (
          <span className="text-[0.65em] font-medium text-brand/70 whitespace-nowrap max-w-[5rem] truncate">
            {delegatedFrom}
          </span>
        )}
        {/* Avatar — click to toggle collapse */}
        <div
          onClick={toggleCollapse}
          className={`flex h-8 w-8 items-center justify-center rounded-full cursor-pointer ${
            isUser
              ? "bg-brand text-white"
              : "bg-neutral-bg3 text-text-secondary"
          }`}
          title={collapsed ? "Click to expand" : "Click to collapse"}
        >
          {isUser ? (
            <User className="h-4 w-4" />
          ) : agentHeadshot ? (
            <img
              src={agentHeadshot}
              alt=""
              className="h-12 w-12 rounded-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
          ) : (
            <span className="text-sm">🤖</span>
          )}
        </div>
      </div>

      {/* Collapse/expand chevron indicator — always visible, clickable */}
      <ChevronRight
        onClick={toggleCollapse}
        className={`h-7 w-7 shrink-0 self-center text-text-primary opacity-70 hover:opacity-100 transition-all cursor-pointer ${
          collapsed ? "" : "rotate-90"
        }`}
      />

      {/* Content */}
      <div
        className={`flex max-w-[80%] flex-col gap-1 ${
          isUser ? "items-end" : "items-start"
        }`}
        style={{ fontSize }}
      >
        {/* User message — markdown-rendered bubble matching orchestrator style */}
        {isUser && (
          <div className="rounded-2xl px-4 py-2.5 bg-brand text-white rounded-br-md">
            {collapsed ? (
              <p className="truncate max-w-[60ch]">{message.content}</p>
            ) : (
              <MarkdownRenderer
                content={message.content ?? ""}
                className="text-white prose-headings:!text-white prose-p:!text-white prose-strong:!text-white prose-li:!text-white prose-blockquote:!text-white prose-code:!text-white"
              />
            )}
          </div>
        )}

        {/* Assistant message — interleaved parts */}
        {!isUser && (
          <div className={`w-full ${
            collapsed ? "" : "space-y-1"
          }`}>
            {/* Status indicators (always shown) */}
            {isError && (
              <div className="flex items-center gap-1.5 text-status-error text-xs px-1">
                <AlertCircle className="h-3.5 w-3.5" />
                <span>{t("chat.error.generating")}</span>
              </div>
            )}
            {isAborted && (
              <div className="flex items-center gap-1.5 text-status-warning text-xs px-1">
                <StopCircle className="h-3.5 w-3.5" />
                <span>{t("chat.error.aborted")}</span>
              </div>
            )}

            {/* Collapsed preview — single truncated line from first text part */}
            {collapsed ? (
              <div className="rounded-2xl bg-neutral-bg2 text-text-primary rounded-bl-md px-4 py-2 truncate max-w-full">
                {(() => {
                  const firstText = parts.find((p) => p.type === "text");
                  if (firstText && firstText.type === "text") {
                    const preview = firstText.text.replace(/\n/g, " ").slice(0, 120);
                    return <span className="text-text-secondary">{preview}{firstText.text.length > 120 ? "…" : ""}</span>;
                  }
                  return <span className="text-text-muted italic">{t("chat.collapsed")}</span>;
                })()}
              </div>
            ) : (
              <>
                {/* Render parts in order. After every tool_call part,
                   emit a chain connector (thick grey left-border bar)
                   to visually link the reasoning chain. */}
                {parts.flatMap((part, i) => {
                  const nextPart = i < parts.length - 1 ? parts[i + 1] : null;
                  const nextIsChainable = nextPart?.type === "tool_call" || nextPart?.type === "thinking";

                  const rendered = (() => {
                    switch (part.type) {
                      case "text":
                        return <TextBlock key={`text-${i}`} text={part.text} isStreaming={isStreaming} />;
                      case "thinking":
                        return <ThinkingBlock key={`think-${i}`} text={part.text} />;
                      case "tool_call":
                        return (
                          <ToolCallDisplay
                            key={part.toolCall.id}
                            toolCall={part.toolCall}
                            isStreaming={isStreaming}
                          />
                        );
                    }
                  })();

                  /* Chain connector — emitted after every tool_call when the
                     next part is also a chainable block (tool or thinking).
                     Thick left border in muted grey, short height. */
                  if (part.type === "tool_call" && nextIsChainable) {
                    return [
                      rendered,
                      <div
                        key={`connector-${i}`}
                        className="ml-3 flex flex-col items-center w-3"
                      >
                        {/* Vertical stem — elongated handle */}
                        <div className="h-4 w-0 border-l-2 border-text-muted/30" />
                        {/* Terminal circle — the "lens" */}
                        <div className="h-2.5 w-2.5 rounded-full border-2 border-text-muted/30" />
                      </div>,
                    ];
                  }
                  return [rendered];
                })}

                {/* Streaming indicator when no parts yet */}
                {isStreaming && parts.length === 0 && (
                  <div className="rounded-2xl bg-neutral-bg2 text-text-primary rounded-bl-md px-4 py-2.5">
                    <StreamingIndicator />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Timestamp — also toggles collapse */}
        <span
          onClick={toggleCollapse}
          className="px-2 text-xs text-text-muted cursor-pointer hover:text-text-secondary transition-colors"
          title={collapsed ? "Click to expand" : "Click to collapse"}
        >
          {timestamp}
        </span>
      </div>
    </article>
  );
});
