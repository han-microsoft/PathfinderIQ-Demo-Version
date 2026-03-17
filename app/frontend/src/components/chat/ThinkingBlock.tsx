/**
 * @module ThinkingBlock
 *
 * Agent reasoning block — renders intermediate thinking steps from
 * the `onThinking` SSE callback.
 *
 * Visually distinct from final-answer text: muted colour, italic font,
 * 💭 thought-bubble icon, and a left border accent in `brand/30`.
 * Communicates to the user that this content is the agent’s internal
 * reasoning chain, not the final answer.
 *
 * The text is rendered through {@link MarkdownRenderer} so inline
 * markdown (bold, code, lists) within thinking blocks is supported.
 *
 * @props
 *   - `text` — the thinking/reasoning string (may contain markdown)
 *
 * @collaborators
 *   - {@link MarkdownRenderer} — renders markdown within the thinking block
 *
 * @dependents
 *   Rendered by {@link MessageBubble} for each `type: 'thinking'` ContentPart.
 */

import { MarkdownRenderer } from "../shared/MarkdownRenderer";

interface ThinkingBlockProps {
  text: string;
}

export function ThinkingBlock({ text }: ThinkingBlockProps) {
  if (!text.trim()) return null;

  return (
    <div className="flex gap-2 border-l-2 border-brand/30 rounded-md bg-neutral-bg2/60 pl-3 pr-3 py-2 my-1">
      <span className="shrink-0">💭</span>
      <div className="text-text-muted italic">
        <MarkdownRenderer content={text} />
      </div>
    </div>
  );
}
