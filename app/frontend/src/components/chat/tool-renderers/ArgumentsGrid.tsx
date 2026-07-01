/**
 * ArgumentsGrid — renders tool call arguments as a clean key-value grid.
 *
 * Replaces raw JSON dump with a two-column layout: parameter name (left,
 * muted label) and value (right, monospace). Nested objects/arrays fall
 * back to compact inline JSON.
 */

interface ArgumentsGridProps {
  args: Record<string, unknown>;
}

export function ArgumentsGrid({ args }: ArgumentsGridProps) {
  const entries = Object.entries(args);
  if (entries.length === 0) return null;

  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[0.85em]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <span className="text-text-muted font-medium">{key}</span>
          <span className="font-mono text-text-secondary whitespace-pre-wrap break-words">
            {formatValue(value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  /* Pretty, indented JSON for objects/arrays so nested args stay readable. */
  return JSON.stringify(value, null, 2);
}
