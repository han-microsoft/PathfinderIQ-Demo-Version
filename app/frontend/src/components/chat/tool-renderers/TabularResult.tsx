/**
 * TabularResult — renders columnar tool results as a styled table.
 *
 * Handles two shapes:
 *   - Fabric GQL / NetworkX: `{columns: string[], data: any[][]}`
 *   - KQL telemetry: `{columns: {name, type}[], rows: object[]}`
 *
 * Features: scrollable container, rounded borders, zebra striping,
 * hover highlight, compact monospace cells. Same visual language as
 * the MarkdownRenderer's table overrides.
 */

interface TabularResultProps {
  result: string;
}

export function TabularResult({ result }: TabularResultProps) {
  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(result);
  } catch {
    return <JsonFallback result={result} />;
  }

  /* Detect shape and normalize to headers + rows */
  let headers: string[];
  let rows: unknown[][];

  if (Array.isArray(parsed.columns) && Array.isArray(parsed.data)) {
    /* Fabric GQL / NetworkX: columns = string[], data = any[][] or object[] */
    headers = parsed.columns.map((c: unknown) =>
      typeof c === "string" ? c : (c as { name?: string }).name ?? String(c)
    );
    /* Rows may be arrays (NetworkX) or objects (Fabric GQL) — normalize both */
    rows = (parsed.data as unknown[]).map((row: unknown) => {
      if (Array.isArray(row)) return row;
      if (row && typeof row === "object") return headers.map((h) => (row as Record<string, unknown>)[h]);
      return [row];
    });
  } else if (Array.isArray(parsed.columns) && Array.isArray(parsed.rows)) {
    /* KQL telemetry: columns = {name, type}[], rows = object[] */
    headers = (parsed.columns as { name: string }[]).map((c) => c.name);
    rows = (parsed.rows as Record<string, unknown>[]).map((row) =>
      headers.map((h) => row[h])
    );
  } else {
    return <JsonFallback result={result} />;
  }

  if (rows.length === 0) {
    return (
      <div className="text-[0.85em] text-text-muted italic py-1">No rows returned</div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border max-h-64 overflow-y-auto">
      <table className="w-full border-collapse text-[0.85em]">
        <thead className="bg-neutral-bg3 text-text-muted text-[0.7em] uppercase tracking-wider sticky top-0">
          <tr>
            {headers.map((h, i) => (
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
          {rows.map((row, ri) => (
            <tr
              key={ri}
              className="transition-colors hover:bg-neutral-bg3/50 even:bg-neutral-bg2/30"
            >
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className="px-3 py-1.5 text-text-secondary border-b border-border/30 whitespace-nowrap font-mono"
                >
                  {formatCell(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    /* Format large numbers with locale separators, small decimals to 4dp */
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toFixed(4);
  }
  if (typeof value === "boolean") return value ? "✓" : "✗";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/** Fallback: syntax-highlighted JSON for unrecognized shapes. */
function JsonFallback({ result }: { result: string }) {
  let formatted: string;
  try {
    formatted = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    formatted = result;
  }
  return (
    <pre className="overflow-x-auto rounded bg-neutral-bg1 p-2 text-[0.85em] font-mono text-text-secondary max-h-48 overflow-y-auto">
      {formatted}
    </pre>
  );
}
