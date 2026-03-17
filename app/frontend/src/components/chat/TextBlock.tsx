/**
 * @module TextBlock
 *
 * Markdown text content part — renders a single `text` ContentPart
 * within an assistant message bubble.
 *
 * Before rendering, the raw text is sanitised by `cleanText()` which
 * strips model artifacts that leak through despite prompt instructions:
 *   - `---QUERY---` … `---ANALYSIS---` recap blocks
 *
 * The cleaned text is passed to {@link MarkdownRenderer} for rich
 * rendering (syntax-highlighted code blocks, links, tables, etc.).
 *
 * During active streaming, markdown rendering is debounced to at most
 * once per 150ms to avoid CPU-heavy react-markdown re-parses on every
 * token (~30–50/sec). Final render fires immediately when streaming ends.
 *
 * @props
 *   - `text` — raw text string from the SSE content part
 *   - `isStreaming` — whether this text block is actively being streamed
 *
 * @collaborators
 *   - {@link MarkdownRenderer} — renders the actual markdown output
 *
 * @dependents
 *   Rendered by {@link MessageBubble} for each `type: 'text'` ContentPart.
 */

import { useState, useEffect, useRef } from "react";
import { MarkdownRenderer } from "../shared/MarkdownRenderer";

interface TextBlockProps {
  text: string;
  isStreaming?: boolean;
}

/** Strip redundant content from the model's text output. */
function cleanText(text: string): string {
  let cleaned = text;
  // Remove ---QUERY--- ... ---ANALYSIS--- recap blocks
  cleaned = cleaned.replace(/---QUERY---[\s\S]*?---ANALYSIS---\s*/g, "");
  return cleaned.trim();
}

/** Debounce interval for markdown rendering during streaming (ms). */
const RENDER_DEBOUNCE_MS = 150;

export function TextBlock({ text, isStreaming = false }: TextBlockProps) {
  const cleaned = cleanText(text);
  // Debounced content — updated at most once per RENDER_DEBOUNCE_MS during streaming
  const [rendered, setRendered] = useState(cleaned);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isStreaming) {
      // Not streaming — render immediately (final state, session reload, etc.)
      setRendered(cleaned);
      return;
    }
    // Streaming — debounce to max 1 markdown re-parse per interval
    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        setRendered(cleaned);
        timerRef.current = null;
      }, RENDER_DEBOUNCE_MS);
    }
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [cleaned, isStreaming]);

  // When streaming ends, flush the final content immediately
  useEffect(() => {
    if (!isStreaming) {
      setRendered(cleaned);
    }
  }, [isStreaming, cleaned]);

  if (!rendered) return null;

  return (
    <div className="rounded-2xl bg-neutral-bg2 text-text-primary rounded-bl-md px-4 py-2.5">
      <MarkdownRenderer content={rendered} />
    </div>
  );
}
