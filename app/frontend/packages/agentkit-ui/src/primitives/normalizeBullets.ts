/**
 * Normalise free-form prose into a markdown bulleted list.
 *
 * Used for renderer fields whose contract is "bullets" but whose upstream
 * producer (an LLM) sometimes emits a single paragraph. We prefer not to
 * let a wall of text reach the UI when a bulleted shape is the intended
 * contract — see `tools/panels/_push_action.py` and the dispatcher /
 * grid_manager prompts for the producer-side rule.
 *
 * Behaviour:
 *   - Empty / null input → "".
 *   - Already-bulleted markdown (any line starts with `-`, `*`, `+`, or
 *     `N.` after optional whitespace) is returned unchanged so the LLM's
 *     intended structure is preserved.
 *   - Otherwise the text is split on paragraph breaks first, then on
 *     line breaks, then as a last resort on sentence boundaries, and
 *     each non-empty chunk is rendered as a `- ` list item.
 *
 * This is a presentation-layer safety net. The producer contract is the
 * source of truth; this exists so existing prose-shaped reasoning still
 * renders legibly without redeploying agents.
 */

const LIST_ITEM = /^\s*(?:[-*+]\s|\d+[.)]\s)/m;

/* Split a single paragraph on sentence boundaries, keeping trailing punctuation.
   Conservative — we only split when at least two sentence endings exist so we
   don't shred a single short sentence into a one-item bullet list. */
function splitSentences(text: string): string[] {
  const matches = text.match(/[^.!?]+[.!?]+(?=\s|$)|[^.!?]+$/g);
  if (!matches || matches.length < 2) return [text];
  return matches.map((s) => s.trim()).filter(Boolean);
}

export function normalizeBullets(content: string | null | undefined): string {
  if (!content) return "";
  const trimmed = content.trim();
  if (!trimmed) return "";

  /* Already bulleted — pass through. */
  if (LIST_ITEM.test(trimmed)) return trimmed;

  /* Paragraph breaks first. */
  let chunks = trimmed.split(/\n{2,}/).map((c) => c.trim()).filter(Boolean);

  /* Single paragraph → fall back to line breaks. */
  if (chunks.length === 1) {
    const lines = chunks[0].split(/\n/).map((c) => c.trim()).filter(Boolean);
    if (lines.length > 1) chunks = lines;
  }

  /* Still one chunk → sentence-split. */
  if (chunks.length === 1) chunks = splitSentences(chunks[0]);

  return chunks.map((c) => `- ${c}`).join("\n");
}
