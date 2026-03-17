/**
 * OptionsCard — renders structured decision options as clickable buttons.
 *
 * When the orchestrator calls `present_options`, the tool result contains
 * structured option data. This renderer displays each option as a card
 * with title, actions, justification, and risks. Clicking an option
 * pre-fills the chat input with the option title so the user can send it.
 *
 * @dependents
 *   Registered in tool-renderers/index.ts for `present_options`.
 */

import { useState } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";
import { parseToolResult } from "./helpers";

interface Option {
  id: number;
  title: string;
  detail: string;
  recommended?: boolean;
}

interface OptionsData {
  type: "options";
  prompt: string;
  options: Option[];
}

interface OptionsCardProps {
  result: string;
}

export function OptionsCard({ result }: OptionsCardProps) {
  const parsed = parseToolResult<OptionsData>(result);
  const [selected, setSelected] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!parsed || !parsed.options || !Array.isArray(parsed.options)) {
    return <pre className="text-xs text-text-muted whitespace-pre-wrap">{result}</pre>;
  }

  const handleSelect = (option: Option) => {
    setSelected(option.id);
    // Send the option as a user message to whichever agent tab is active.
    const sessionId = useSessionStore.getState().activeSessionId;
    const agentId = useAgentStore.getState().activeAgentId || "orchestrator";
    if (sessionId) {
      useChatStore.getState().sendMessage(
        sessionId,
        option.title,
        agentId,
      );
    }
  };

  return (
    <div className="space-y-3 text-xs">
      {/* Prompt */}
      <p className="text-text-secondary font-medium">{parsed.prompt}</p>

      {/* Option cards */}
      <div className="space-y-2">
        {parsed.options.map((opt) => {
          const isSelected = selected === opt.id;
          const isExpanded = expanded === opt.id;

          return (
            <div
              key={opt.id}
              className={`border rounded-lg overflow-hidden transition-colors ${
                isSelected
                  ? "border-accent-primary bg-accent-primary/5"
                  : opt.recommended
                    ? "border-status-success/50 bg-status-success/5"
                    : "border-border"
              }`}
            >
              {/* Header — clickable to expand details */}
              <button
                className="w-full text-left px-3 py-2 flex items-center gap-2"
                onClick={() => setExpanded(isExpanded ? null : opt.id)}
              >
                <span className="font-mono text-text-muted text-[10px] shrink-0">
                  {opt.id}
                </span>
                <span className="font-semibold text-text-primary flex-1">
                  {opt.title}
                </span>
                {opt.recommended && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold text-status-success bg-status-success/10">
                    Recommended
                  </span>
                )}
                <span className="text-text-muted text-[10px]">
                  {isExpanded ? "▲" : "▼"}
                </span>
              </button>

              {/* Details — shown when expanded */}
              {isExpanded && (
                <div className="px-3 pb-2 space-y-1.5 border-t border-border/50">
                  <p className="text-text-secondary whitespace-pre-line">{opt.detail}</p>
                </div>
              )}

              {/* Select button */}
              {!isSelected && (
                <div className="px-3 pb-2">
                  <button
                    className={`w-full py-1.5 rounded text-xs font-semibold transition-colors ${
                      opt.recommended
                        ? "bg-accent-primary text-white hover:bg-accent-primary/90"
                        : "bg-neutral-bg3 text-text-primary hover:bg-neutral-bg3/80"
                    }`}
                    onClick={() => handleSelect(opt)}
                  >
                    Select{opt.recommended ? " (Recommended)" : ""}
                  </button>
                </div>
              )}

              {/* Selected indicator */}
              {isSelected && (
                <div className="px-3 pb-2 text-center text-status-success font-semibold">
                  ✓ Selected — sending…
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
