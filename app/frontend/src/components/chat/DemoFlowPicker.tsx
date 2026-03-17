/**
 * DemoFlowPicker — nested dropdown for selecting a demo flow step prompt.
 *
 * Purpose:
 *   Two-level dropdown: first click shows available demo flows (titles),
 *   second click expands a flow to show its steps (prompts).  Selecting
 *   a step fires the ``onSelect`` callback with the prompt text, which
 *   the parent (ChatInput) sends as a message.
 *
 * Isolation:
 *   Pure rendering component.  No store imports.  Reads demo_flows
 *   from the ``ScenarioInfo`` type passed as a prop.
 *
 * Key collaborators:
 *   - components/chat/ChatInput.tsx — renders this next to the textarea
 *   - hooks/useScenario.ts — provides ScenarioInfo with demo_flows
 *
 * Dependents:
 *   Called by: ChatInput.tsx only
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { ChevronDown, Play } from "lucide-react";

/** A single demo flow with a title and ordered step prompts. */
export interface DemoFlow {
  title: string;
  steps: { prompt: string }[];
}

interface DemoFlowPickerProps {
  /** Available demo flows from scenario.yaml. */
  flows: DemoFlow[];
  /** Called when the user selects a step prompt. */
  onSelect: (prompt: string) => void;
  /** Whether the picker should be disabled (e.g. during streaming). */
  disabled?: boolean;
}

/**
 * Two-level dropdown: Flow titles → Step prompts.
 * Click outside or select a step to close.
 */
export function DemoFlowPicker({ flows, onSelect, disabled }: DemoFlowPickerProps) {
  /* Whether the main dropdown is open */
  const [open, setOpen] = useState(false);
  /* Index of the currently expanded flow (null = none) */
  const [expandedFlow, setExpandedFlow] = useState<number | null>(null);
  /* Ref for click-outside detection */
  const containerRef = useRef<HTMLDivElement>(null);

  /** Close dropdown when clicking outside. */
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setExpandedFlow(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  /** Toggle the main dropdown. */
  const toggle = useCallback(() => {
    if (disabled) return;
    setOpen((v) => {
      if (v) setExpandedFlow(null);
      return !v;
    });
  }, [disabled]);

  /** Handle flow title click — expand/collapse that flow's steps. */
  const handleFlowClick = useCallback((idx: number) => {
    setExpandedFlow((prev) => (prev === idx ? null : idx));
  }, []);

  /** Handle step selection — fire callback, close dropdown. */
  const handleStepClick = useCallback(
    (prompt: string) => {
      onSelect(prompt);
      setOpen(false);
      setExpandedFlow(null);
    },
    [onSelect]
  );

  if (flows.length === 0) return null;

  return (
    <div ref={containerRef} className="relative">
      {/* Trigger button */}
      <button
        type="button"
        onClick={toggle}
        disabled={disabled}
        className={`flex items-center gap-2 px-4 py-3 rounded-2xl border transition-colors text-sm font-medium whitespace-nowrap ${
          disabled
            ? "bg-brand/30 text-white/40 border-transparent cursor-not-allowed"
            : "bg-brand text-white border-transparent hover:bg-brand-hover"
        }`}
        title="Run a demo flow"
      >
        <Play className="h-4 w-4" />
        Demo Flows
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Dropdown panel — opens upward (above the chat input) */}
      {open && (
        <div className="absolute bottom-full mb-2 left-0 w-[28rem] max-h-[60vh] overflow-y-auto rounded-xl border border-border bg-neutral-bg2 shadow-2xl z-50">
          {flows.map((flow, fi) => (
            <div key={fi}>
              {/* Flow title row */}
              <button
                type="button"
                onClick={() => handleFlowClick(fi)}
                className={`w-full text-left px-4 py-3 text-sm font-semibold flex items-center justify-between transition-colors ${
                  expandedFlow === fi
                    ? "bg-brand/10 text-brand"
                    : "text-text-primary hover:bg-neutral-bg3"
                } ${fi > 0 ? "border-t border-border" : ""}`}
              >
                <span className="pr-2 leading-snug">{flow.title}</span>
                <ChevronDown
                  className={`h-4 w-4 shrink-0 transition-transform ${
                    expandedFlow === fi ? "rotate-180" : ""
                  }`}
                />
              </button>

              {/* Steps — shown when flow is expanded */}
              {expandedFlow === fi && (
                <div className="border-t border-border bg-neutral-bg1">
                  {flow.steps.map((step, si) => (
                    <button
                      key={si}
                      type="button"
                      onClick={() => handleStepClick(step.prompt)}
                      className="w-full text-left px-5 py-3 text-sm text-text-secondary hover:bg-neutral-bg3 hover:text-text-primary transition-colors border-b border-border last:border-b-0 leading-relaxed"
                    >
                      <span className="text-text-muted mr-1.5 font-mono">
                        {si + 1}.
                      </span>
                      {/* Show first 120 chars of the prompt as a preview */}
                      {step.prompt.length > 120
                        ? step.prompt.slice(0, 120) + "…"
                        : step.prompt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
