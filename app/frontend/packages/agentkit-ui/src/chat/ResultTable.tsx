/**
 * ResultTable — shared scrollable table primitive for tool result tables.
 *
 * Module role:
 *   Single implementation of the thead/tbody/`formatCell` pattern that
 *   was hand-rolled three times (TabularResult / GraphResult /
 *   GraphEnvelopeResult.ListSection). Consumed by all three and any
 *   future tool that returns a `{headers, rows}` shape.
 *
 * Features:
 *   - `previewRows` (default 5) collapses long tables to a preview with
 *     a "show all (N more)" / "collapse" toggle. The benchmark surface
 *     (GraphEnvelopeResult) had no preview cap and grows the chat scroll
 *     unbounded on 30-row responses — this primitive retires that.
 *   - `prominentColumns` lets the registry tag the high-signal columns
 *     for a tool. Non-prominent columns render in `text-text-muted`
 *     behind a "metadata" toggle so the eye lands on the signal first.
 *   - All sizing/colour utilities are tokens. No `text-[…]` arbitrary
 *     values are allowed inside this file (audit invariant).
 */

import { useState } from "react";
import { formatCell } from "./helpers";

export interface ResultTableProps {
  headers: string[];
  rows: unknown[][];
  /**
   * Number of rows to render in the collapsed state. Default 5. Set to
   * Infinity (or rows.length) to disable the preview cap.
   */
  previewRows?: number;
  /**
   * Column names treated as the salient signal. Non-prominent columns
   * render in muted text behind a "metadata" toggle. When empty (the
   * default) every column is treated as prominent — preserves the
   * pre-R6 visual shape for tools that have not declared hints yet.
   */
  prominentColumns?: string[];
  /** Optional outer max-height override. Use sparingly. */
  maxHeightClass?: string;
}

const DEFAULT_PREVIEW = 5;

export function ResultTable({
  headers,
  rows,
  previewRows = DEFAULT_PREVIEW,
  prominentColumns,
  maxHeightClass = "max-h-64",
}: ResultTableProps) {
  /* Preview-row expansion. Initial state shows up to `previewRows`. */
  const [showAll, setShowAll] = useState(false);
  /* Metadata-column toggle. Initial state hides non-prominent columns
     when the registry hinted at prominent ones. */
  const hasProminentHint = !!prominentColumns && prominentColumns.length > 0;
  const [showMetadata, setShowMetadata] = useState(!hasProminentHint);

  const prominentSet = new Set(prominentColumns ?? []);
  const visibleColumnIdx = headers
    .map((h, i) => ({ h, i }))
    .filter(({ h }) => (showMetadata ? true : !hasProminentHint || prominentSet.has(h)));
  const hiddenMetadataCount = headers.length - visibleColumnIdx.length;

  const limit = showAll ? rows.length : Math.min(previewRows, rows.length);
  const visibleRows = rows.slice(0, limit);
  const hiddenRowCount = rows.length - limit;

  return (
    <div className="flex flex-col gap-1">
      {(hasProminentHint || rows.length > previewRows) && (
        <div className="flex items-center justify-end gap-2 text-label text-text-muted">
          {hasProminentHint && hiddenMetadataCount > 0 && !showMetadata && (
            <button
              type="button"
              onClick={() => setShowMetadata(true)}
              className="hover:text-text-secondary transition-colors"
            >
              show metadata ({hiddenMetadataCount})
            </button>
          )}
          {hasProminentHint && showMetadata && (
            <button
              type="button"
              onClick={() => setShowMetadata(false)}
              className="hover:text-text-secondary transition-colors"
            >
              hide metadata
            </button>
          )}
        </div>
      )}
      <div className={`overflow-x-auto rounded-lg border border-border ${maxHeightClass} overflow-y-auto`}>
        <table className="w-full border-collapse text-xs">
          <thead className="bg-neutral-bg3 text-text-muted text-label uppercase tracking-wider sticky top-0">
            <tr>
              {visibleColumnIdx.map(({ h, i }) => (
                <th
                  key={i}
                  className="px-3 py-2 text-left font-semibold border-b border-border whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, ri) => (
              <tr
                key={ri}
                className="transition-colors hover:bg-neutral-bg3/50 even:bg-neutral-bg2/30"
              >
                {visibleColumnIdx.map(({ i }) => {
                  const isProminent = !hasProminentHint || prominentSet.has(headers[i]);
                  return (
                    <td
                      key={i}
                      className={`px-3 py-1.5 border-b border-border/30 whitespace-nowrap font-mono ${
                        isProminent ? "text-text-secondary" : "text-text-muted"
                      }`}
                    >
                      {formatCell(row[i])}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hiddenRowCount > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="self-start text-label text-text-muted hover:text-text-secondary transition-colors"
        >
          show all ({hiddenRowCount} more)
        </button>
      )}
      {showAll && rows.length > previewRows && (
        <button
          type="button"
          onClick={() => setShowAll(false)}
          className="self-start text-label text-text-muted hover:text-text-secondary transition-colors"
        >
          collapse
        </button>
      )}
    </div>
  );
}
