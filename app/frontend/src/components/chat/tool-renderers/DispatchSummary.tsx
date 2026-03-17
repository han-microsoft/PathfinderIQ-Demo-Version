/**
 * DispatchSummary — renders dispatch_field_engineer results as a definition list.
 *
 * Handles the shape: `{status, dispatch_id, engineer: {...}, destination: {...}, urgency, ...}`
 * Renders as a compact grid of labeled values with urgency color-coding.
 */

import { severityColor as getSeverityColor, parseToolResult } from "./helpers";

interface DispatchSummaryProps {
  result: string;
}

export function DispatchSummary({ result }: DispatchSummaryProps) {
  const parsed = parseToolResult(result);
  if (!parsed) {
    return <FallbackJson result={result} />;
  }

  if (!parsed.dispatch_id) {
    return <FallbackJson result={result} />;
  }

  const engineer = parsed.engineer as Record<string, unknown> | undefined;
  const destination = parsed.destination as Record<string, unknown> | undefined;
  const urgency = String(parsed.urgency ?? "").toUpperCase();
  const badgeClass = getSeverityColor(urgency);

  return (
    <div className="space-y-3 text-xs">
      {/* Dispatch header */}
      <div className="flex items-center gap-2">
        <span className="text-status-success font-semibold">✓ Dispatched</span>
        <span className="font-mono text-text-muted">{String(parsed.dispatch_id)}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${badgeClass}`}>
          {urgency}
        </span>
      </div>

      <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        {/* Engineer details */}
        {engineer && (
          <>
            <Label>Engineer</Label>
            <Value>{String(engineer.name ?? "—")}</Value>
            <Label>Email</Label>
            <Value>{String(engineer.email ?? "—")}</Value>
            <Label>Phone</Label>
            <Value>{String(engineer.phone ?? "—")}</Value>
          </>
        )}

        {/* Destination */}
        {destination && (
          <>
            <Label>Destination</Label>
            <Value>{String(destination.description || "—")}</Value>
            <Label>GPS</Label>
            <Value>
              {String(destination.latitude)}, {String(destination.longitude)}
            </Value>
          </>
        )}

        {/* Sensors */}
        {parsed.sensor_ids != null && (() => {
          const ids = parsed.sensor_ids;
          const text: string = Array.isArray(ids)
            ? (ids as string[]).join(", ")
            : String(ids);
          return (
            <>
              <Label>Sensors</Label>
              <Value>{text}</Value>
            </>
          );
        })()}
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <span className="text-text-muted font-medium">{children}</span>;
}

function Value({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-text-secondary break-all">{children}</span>
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
