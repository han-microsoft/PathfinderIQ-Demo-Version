/**
 * QueryArgs — pretty-printer for query-bearing tool calls.
 *
 * The graph/alerts/telemetry tools take a single dense `query` string
 * (Gremlin, Cypher/GQL `MATCH…RETURN`, or KQL pipe queries). Rendered raw
 * they are one long unreadable line. This renderer detects the dialect and
 * reflows it onto clean, uniformly-indented lines in a monospace block.
 *
 * Registered for query_graph / query_graph_local / query_telemetry /
 * query_alerts in tool-renderers/index.ts.
 */

interface QueryArgsProps {
  args: Record<string, unknown>;
}

/** Break a Gremlin traversal onto one step per line (paren/quote aware). */
function formatGremlin(q: string): string {
  let out = "";
  let depth = 0;
  let inSq = false;
  let inDq = false;
  for (let i = 0; i < q.length; i += 1) {
    const c = q[i];
    if (inSq) { out += c; if (c === "'") inSq = false; continue; }
    if (inDq) { out += c; if (c === '"') inDq = false; continue; }
    if (c === "'") { inSq = true; out += c; continue; }
    if (c === '"') { inDq = true; out += c; continue; }
    if (c === "(") { depth += 1; out += c; continue; }
    if (c === ")") { depth -= 1; out += c; continue; }
    if (c === "." && depth === 0 && i > 0) { out += "\n  ."; continue; }
    out += c;
  }
  return out;
}

/** Detect the query dialect and reflow it into readable, indented lines. */
export function formatQuery(raw: string): string {
  const q = raw.trim();
  if (!q) return q;

  // KQL pipe style: "Table | where … | top … | project …"
  if (/^\w[\w.]*\s*\|/.test(q) || /\s\|\s/.test(q)) {
    return q
      .split("|")
      .map((seg, i) => (i === 0 ? seg.trim() : `| ${seg.trim()}`))
      .filter((s) => s.length > 0)
      .join("\n");
  }

  // Cypher / GQL: MATCH … WHERE … RETURN …
  if (/\bMATCH\b/i.test(q) || /\bRETURN\b/i.test(q)) {
    return q
      .replace(
        /\s+(OPTIONAL MATCH|MATCH|WHERE|RETURN|ORDER BY|WITH|UNWIND|LIMIT|SKIP|CREATE|MERGE|SET|DELETE)\b/gi,
        (_m, kw) => `\n${kw}`,
      )
      .trim();
  }

  // Gremlin: g.V()… → one step per line.
  if (/^g\./.test(q)) return formatGremlin(q);

  return q;
}

export function QueryArgs({ args }: QueryArgsProps) {
  const query = typeof args.query === "string" ? args.query : null;
  const rest = Object.entries(args).filter(([k]) => k !== "query");

  return (
    <div className="space-y-2 text-[0.85em]">
      {query != null && (
        <pre className="font-mono text-[0.92em] leading-relaxed whitespace-pre-wrap break-words rounded-md bg-neutral-bg1 border border-border/30 p-3 text-text-secondary overflow-x-auto">
          {formatQuery(query)}
        </pre>
      )}
      {rest.length > 0 && (
        <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          {rest.map(([k, v]) => (
            <div key={k} className="contents">
              <span className="text-text-muted font-medium">{k}</span>
              <span className="font-mono text-text-secondary whitespace-pre-wrap break-words">
                {typeof v === "string" ? v : JSON.stringify(v, null, 2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
