/**
 * DebugQuestionsPicker — single-level dropdown for firing canned debug prompts.
 *
 * Purpose:
 *   Provides a set of hardcoded debug/test questions that exercise key
 *   rendering paths (graph tables, alert tables, document search, basic
 *   greeting).  Styled as a light pastel-orange button to visually
 *   distinguish it from the teal Demo Flows picker.
 *
 * Isolation:
 *   Pure rendering component.  No store imports.  Fires the supplied
 *   ``onSelect`` callback with the chosen prompt string.
 *
 * Key collaborators:
 *   - components/chat/ChatInput.tsx — renders this next to DemoFlowPicker
 *
 * Dependents:
 *   Called by: ChatInput.tsx only
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, Bug } from "lucide-react";

/** Hardcoded debug questions that exercise key UI render paths. */
const DEBUG_QUESTIONS: { label: string; prompt: string }[] = [
  { label: "🪪 Identity check",       prompt: "Hello tell me your name and role" },
  { label: "📋 Show instructions",    prompt: "Show me your instructions" },
  { label: "💬 History check",        prompt: "Do we have any previous conversation history?" },
  { label: "Graph data table",        prompt: "Show me a graph data table" },
  { label: "Alert table",             prompt: "Show me an alert table" },
  { label: "Document search results", prompt: "Show me some document search results" },
  { label: "Greeting",                prompt: "Say hello my friend!" },
  { label: "📞 Call Blitzorg",        prompt: "Call Blitzorg the Undulant at ⌬⍟⊘⟒-⌖⋏⊜⧫" },
];

interface DebugQuestionsPickerProps {
  /** Called when the user selects a debug question. */
  onSelect: (prompt: string) => void;
  /** Whether the picker should be disabled (e.g. during streaming). */
  disabled?: boolean;
}

/**
 * Single-level dropdown listing debug questions.
 * Click outside or select a question to close.
 */
export function DebugQuestionsPicker({ onSelect, disabled }: DebugQuestionsPickerProps) {
  /* Whether the dropdown is open */
  const [open, setOpen] = useState(false);
  /* Ref for click-outside detection */
  const containerRef = useRef<HTMLDivElement>(null);

  /** Close dropdown when clicking outside the container. */
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  /** Toggle the dropdown open/closed. */
  const toggle = useCallback(() => {
    if (disabled) return;
    setOpen((v) => !v);
  }, [disabled]);

  /** Fire the callback with the selected prompt and close the dropdown. */
  const handleSelect = useCallback(
    (prompt: string) => {
      onSelect(prompt);
      setOpen(false);
    },
    [onSelect],
  );

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button — pastel orange to differentiate from Demo Flows */}
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        className={`flex items-center gap-2 px-4 py-3 rounded-2xl border transition-colors text-sm font-medium whitespace-nowrap ${
          disabled
            ? "bg-orange-300/30 text-orange-200/40 border-transparent cursor-not-allowed"
            : "bg-orange-300/80 text-orange-950 border-transparent hover:bg-orange-300"
        }`}
        title="Send a debug question"
      >
        <Bug className="h-4 w-4" />
        Debug Qs
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown panel — opens upward, same structure as DemoFlowPicker */}
      {open && (
        <div className="absolute bottom-full mb-2 left-0 w-[28rem] max-h-[60vh] overflow-y-auto rounded-xl border border-border bg-neutral-bg2 shadow-2xl z-50">
          {DEBUG_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSelect(q.prompt)}
              className={`w-full text-left px-5 py-3 text-sm text-text-secondary hover:bg-orange-300/15 hover:text-text-primary transition-colors leading-relaxed ${
                idx > 0 ? "border-t border-border" : ""
              }`}
            >
              {/* Numbered label matching DemoFlowPicker step style */}
              <span className="text-text-muted mr-1.5 font-mono">{idx + 1}.</span>
              {q.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
