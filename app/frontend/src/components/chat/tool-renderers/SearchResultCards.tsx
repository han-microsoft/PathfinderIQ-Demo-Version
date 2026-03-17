/**
 * SearchResultCards — renders search tool results as a stacked card list.
 *
 * Handles the shape: `{results: [{title, source, score, text}], count: N}`
 * Renders each result as a compact card with title, relevance score badge,
 * source tag, and a truncated text preview. Clicking a card opens a full
 * markdown overlay with a text size slider.
 */

import { useState, useEffect } from "react";
import { MarkdownRenderer } from "../../shared/MarkdownRenderer";

interface SearchResultCardsProps {
  result: string;
}

interface SearchResult {
  title: string;
  source: string;
  score: number;
  text: string;
}

export function SearchResultCards({ result }: SearchResultCardsProps) {
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);

  let parsed: { results?: SearchResult[]; count?: number };
  try {
    parsed = JSON.parse(result);
  } catch {
    return <FallbackJson result={result} />;
  }

  const results = parsed.results;
  if (!Array.isArray(results) || results.length === 0) {
    return (
      <div className="text-xs text-text-muted italic py-1">No results found</div>
    );
  }

  return (
    <>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {results.map((r, i) => (
          <div
            key={i}
            className="rounded-lg border border-border/50 bg-neutral-bg1 px-3 py-2 space-y-1 cursor-pointer hover:border-brand/40 hover:bg-brand/5 transition-colors"
            onClick={() => setSelectedResult(r)}
            title="Click to expand"
          >
            {/* Title + score */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-text-primary truncate flex-1">
                {r.title || "Untitled"}
              </span>
              {r.score != null && (
                <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-brand/10 text-brand font-mono font-medium">
                  {r.score.toFixed(2)}
                </span>
              )}
            </div>
            {/* Source */}
            {r.source && (
              <div className="text-[10px] text-text-muted truncate">{r.source}</div>
            )}
            {/* Text preview */}
            <p className="text-xs text-text-secondary leading-relaxed line-clamp-3">
              {r.text}
            </p>
          </div>
        ))}
      </div>

      {/* Full document overlay */}
      {selectedResult && (
        <SearchResultOverlay
          result={selectedResult}
          onClose={() => setSelectedResult(null)}
        />
      )}
    </>
  );
}

/** Full-viewport overlay showing a search result as formatted markdown. */
function SearchResultOverlay({
  result,
  onClose,
}: {
  result: SearchResult;
  onClose: () => void;
}) {
  const [textScale, setTextScale] = useState(100);

  /* Close on Escape */
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[85vh] mx-4 rounded-xl bg-neutral-bg1 border border-border shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-neutral-bg2">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-bold text-text-primary truncate">
              {result.title || "Document"}
            </h3>
            <div className="flex items-center gap-3 mt-1">
              {result.source && (
                <span className="text-[11px] text-text-muted truncate max-w-[300px]">
                  {result.source}
                </span>
              )}
              <span className="text-[11px] px-1.5 py-0.5 rounded bg-brand/10 text-brand font-mono font-medium">
                Score: {result.score.toFixed(3)}
              </span>
            </div>
          </div>
          {/* Text scale slider */}
          <div className="flex items-center gap-2 shrink-0 ml-4">
            <input
              type="range"
              min={70}
              max={180}
              step={5}
              value={textScale}
              onChange={(e) => setTextScale(Number(e.target.value))}
              className="accent-brand cursor-pointer"
              style={{ width: "80px", height: "4px" }}
              title={`Text scale: ${textScale}%`}
            />
            <span className="text-[10px] font-mono text-text-muted w-8 text-right">
              {textScale}%
            </span>
          </div>
          {/* Close button */}
          <button
            onClick={onClose}
            className="ml-3 text-text-muted hover:text-text-primary text-lg transition-colors"
            title="Close"
          >
            ✕
          </button>
        </div>

        {/* Scrollable markdown content */}
        <div
          className="overflow-y-auto p-5"
          style={{ fontSize: `${Math.round(14 * textScale / 100)}px` }}
        >
          <div className="prose prose-invert max-w-none text-text-secondary [font-size:inherit]">
            <MarkdownRenderer content={result.text} />
          </div>
        </div>
      </div>
    </div>
  );
}

function FallbackJson({ result }: { result: string }) {
  let formatted: string;
  try {
    formatted = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    formatted = result;
  }
  return (
    <pre className="overflow-x-auto rounded bg-neutral-bg1 p-2 text-xs font-mono text-text-secondary max-h-48 overflow-y-auto">
      {formatted}
    </pre>
  );
}
