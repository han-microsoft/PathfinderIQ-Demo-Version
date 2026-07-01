/**
 * ActionResult — uniform card for the "action" tools that mutate or create
 * something and return a small status envelope.
 *
 * Covers (inferred from the result fields, so no tool name needed):
 *   - reroute_traffic        {status:"rerouted", path_id, activated_at, reason}
 *   - set_link_status        {status:"admin_down"|"admin_up", link_id, changed_at}
 *   - create_incident_ticket {ticket_id, status, severity, title, assigned_to, url}
 *   - update_advisory        {advisory_id, status, message, distribution_count}
 *
 * Renders a consistent header (icon + verb + status pill), a tidy field grid
 * (IDs monospace, timestamps localised), an optional note, and an optional
 * link — instead of a raw JSON blob.
 */

import { Fragment, type ReactNode } from "react";
import { parseToolResult } from "./helpers";

interface ActionResultProps {
  result: string;
}

type Kind = "reroute" | "link" | "ticket" | "advisory" | "generic";

function classify(p: Record<string, unknown>): Kind {
  if ("path_id" in p || "path" in p) return "reroute";
  if ("link_id" in p || "link" in p) return "link";
  if ("ticket_id" in p) return "ticket";
  if ("advisory_id" in p) return "advisory";
  return "generic";
}

/** Map a status verb to a coloured pill tone. */
function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (["admin_down", "down", "offline"].includes(s))
    return "text-status-warning bg-status-warning/10";
  if (["failed", "error", "rejected"].includes(s))
    return "text-status-error bg-status-error/10";
  // rerouted / admin_up / posted / open / dispatched / active / done …
  return "text-status-success bg-status-success/10";
}

function fmtTime(v: unknown): string {
  const s = String(v);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString();
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-text-secondary break-all">{children}</span>;
}

function tryPretty(result: string): string {
  try {
    return JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    return result;
  }
}

export function ActionResult({ result }: ActionResultProps) {
  const p = parseToolResult(result) as Record<string, unknown> | null;
  if (!p) {
    return (
      <pre className="font-mono text-[0.85em] whitespace-pre-wrap break-words text-text-secondary">
        {tryPretty(result)}
      </pre>
    );
  }

  const kind = classify(p);
  if (kind === "generic") {
    return (
      <pre className="font-mono text-[0.85em] whitespace-pre-wrap break-words text-text-secondary">
        {tryPretty(result)}
      </pre>
    );
  }

  const status = String(p.status ?? "");

  const header: Record<Exclude<Kind, "generic">, { icon: string; title: string }> = {
    reroute: { icon: "🔀", title: "Traffic rerouted" },
    link: { icon: status === "admin_down" ? "⛔" : "✅", title: "Link status changed" },
    ticket: { icon: "🎫", title: "Incident ticket created" },
    advisory: { icon: "📣", title: "Customer advisory posted" },
  };
  const head = header[kind];

  const rows: Array<[string, ReactNode]> = [];
  let note: string | null = null;
  let url: string | null = null;

  if (kind === "reroute") {
    rows.push(["Backup path", <Mono>{String(p.path_id ?? p.path ?? "—")}</Mono>]);
    if (p.activated_at) rows.push(["Activated", fmtTime(p.activated_at)]);
    if (p.reason) note = String(p.reason);
  } else if (kind === "link") {
    rows.push(["Link", <Mono>{String(p.link_id ?? p.link ?? "—")}</Mono>]);
    if (p.changed_at) rows.push(["Changed", fmtTime(p.changed_at)]);
  } else if (kind === "ticket") {
    rows.push(["Ticket", <Mono>{String(p.ticket_id ?? "—")}</Mono>]);
    if (p.severity) rows.push(["Severity", String(p.severity)]);
    if (p.assigned_to) rows.push(["Assigned to", String(p.assigned_to)]);
    if (p.title) note = String(p.title);
    if (typeof p.url === "string") url = p.url;
  } else if (kind === "advisory") {
    rows.push(["Advisory", <Mono>{String(p.advisory_id ?? "—")}</Mono>]);
    if (p.distribution_count != null)
      rows.push(["Recipients", String(p.distribution_count)]);
    if (p.message) note = String(p.message);
  }

  return (
    <div className="space-y-2.5 text-xs">
      {/* Header: icon + verb + status pill */}
      <div className="flex items-center gap-2">
        <span className="text-sm leading-none">{head.icon}</span>
        <span className="font-semibold text-text-primary">{head.title}</span>
        {status && (
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${statusTone(status)}`}
          >
            {status.replace(/_/g, " ")}
          </span>
        )}
      </div>

      {/* Field grid */}
      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        {rows.map(([k, v]) => (
          <Fragment key={k}>
            <span className="text-text-muted font-medium">{k}</span>
            <span className="text-text-secondary break-words">{v}</span>
          </Fragment>
        ))}
      </div>

      {/* Note (reason / title / message) */}
      {note && (
        <div className="rounded bg-neutral-bg1 border border-border/30 p-2 text-text-secondary leading-relaxed">
          {note}
        </div>
      )}

      {/* Link */}
      {url && (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="inline-block font-mono text-brand hover:underline break-all"
        >
          {url}
        </a>
      )}
    </div>
  );
}
