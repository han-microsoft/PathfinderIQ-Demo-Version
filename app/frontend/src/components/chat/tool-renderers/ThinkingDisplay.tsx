/**
 * @module ThinkingDisplay
 *
 * Renders the `thinking` tool call as an inline thought bubble.
 * Shows only the `thoughts` argument text — no "Arguments"/"Result"
 * labels, no expandable JSON. Always visible (not collapsible).
 *
 * @props
 *   - `thoughts` — the agent's reasoning text
 *
 * @dependents
 *   Rendered by {@link ToolCallDisplay} when `toolCall.name === "thinking"`.
 */

interface ThinkingDisplayProps {
  thoughts: string;
}

export function ThinkingDisplay({ thoughts }: ThinkingDisplayProps) {
  return (
    <div className="my-2 border-t border-b border-l-[3px] border-border border-l-brand/50 rounded-l-md bg-neutral-bg2/60 py-3">
      <div className="flex items-center gap-2 px-3">
        <span className="shrink-0">💭</span>
        <p className="text-text-muted italic text-[0.92em] leading-relaxed whitespace-pre-wrap">
          {thoughts}
        </p>
      </div>
    </div>
  );
}
