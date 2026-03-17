/**
 * JsonFallback — generic syntax-highlighted JSON dump for unrecognized tool results.
 *
 * Used when no specialized renderer matches the tool name or result shape.
 * Pretty-prints the JSON with 2-space indentation in a scrollable <pre> block.
 */

interface JsonFallbackProps {
  result: string;
}

export function JsonFallback({ result }: JsonFallbackProps) {
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
