/**
 * BlastRadiusResult — executive impact card for `estimate_blast_radius`.
 *
 * Turns the blast-radius rollup into a CIO-friendly summary: headline stat
 * tiles (users affected, $/hr SLA exposure, contract value at risk, projected
 * cost), a per-service breakdown table, the examined-but-ruled-out services
 * (bounded blast radius), and a methodology footnote.
 *
 * Shape: {affected_user_count, services[], total_sla_penalty_per_hour_usd,
 *         contract_value_at_risk_usd, projection:{outage_hours, projected_cost_usd},
 *         not_affected[], methodology}
 */

import { parseToolResult } from "./helpers";

interface BlastRadiusResultProps {
  result: string;
}

interface ServiceRow {
  id?: string;
  type?: string;
  users?: number;
  sla?: string | null;
  penalty_per_hour_usd?: number;
}

function fmtUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}k`;
  return `$${n.toLocaleString()}`;
}

function fmtNum(n: number): string {
  return n.toLocaleString();
}

function Stat({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div className="flex-1 min-w-[110px] rounded-lg border border-border/30 bg-neutral-bg1 px-3 py-2">
      <div className={`text-base font-bold leading-tight ${accent ? "text-status-error" : "text-text-primary"}`}>
        {value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-text-muted mt-0.5">{label}</div>
    </div>
  );
}

export function BlastRadiusResult({ result }: BlastRadiusResultProps) {
  const p = parseToolResult(result) as Record<string, unknown> | null;
  if (!p || p.affected_user_count == null) {
    return (
      <pre className="font-mono text-[0.85em] whitespace-pre-wrap break-words text-text-secondary">
        {result}
      </pre>
    );
  }

  const users = Number(p.affected_user_count ?? 0);
  const penaltyPerHour = Number(p.total_sla_penalty_per_hour_usd ?? 0);
  const contractAtRisk = Number(p.contract_value_at_risk_usd ?? 0);
  const projection = (p.projection as Record<string, unknown>) ?? {};
  const projectedCost = Number(projection.projected_cost_usd ?? 0);
  const outageHours = Number(projection.outage_hours ?? 0);
  const services = Array.isArray(p.services) ? (p.services as ServiceRow[]) : [];
  const notAffected = Array.isArray(p.not_affected) ? (p.not_affected as string[]) : [];
  const methodology = typeof p.methodology === "string" ? p.methodology : null;

  return (
    <div className="space-y-3 text-xs">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="text-sm leading-none">💥</span>
        <span className="font-semibold text-text-primary">Blast radius &amp; financial exposure</span>
      </div>

      {/* Headline stat tiles */}
      <div className="flex flex-wrap gap-2">
        <Stat value={fmtNum(users)} label="Users affected" />
        <Stat value={`${fmtUsd(penaltyPerHour)}/hr`} label="SLA exposure" accent />
        {contractAtRisk > 0 && <Stat value={fmtUsd(contractAtRisk)} label="Contract at risk" />}
        {projectedCost > 0 && (
          <Stat value={fmtUsd(projectedCost)} label={`Est. ${outageHours}h cost`} accent />
        )}
      </div>

      {/* Per-service breakdown */}
      {services.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border/30">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-text-muted border-b border-border/30">
                <th className="text-left font-medium px-2 py-1">Service</th>
                <th className="text-left font-medium px-2 py-1">Type</th>
                <th className="text-right font-medium px-2 py-1">Users</th>
                <th className="text-left font-medium px-2 py-1">SLA</th>
                <th className="text-right font-medium px-2 py-1">$/hr</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s, i) => (
                <tr key={s.id ?? i} className="border-b border-border/20 last:border-0">
                  <td className="px-2 py-1 font-mono text-text-secondary">{s.id ?? "—"}</td>
                  <td className="px-2 py-1 text-text-secondary">{s.type ?? "—"}</td>
                  <td className="px-2 py-1 text-right text-text-secondary">{fmtNum(Number(s.users ?? 0))}</td>
                  <td className="px-2 py-1 text-text-secondary">{s.sla ?? "—"}</td>
                  <td className="px-2 py-1 text-right text-text-secondary">
                    {Number(s.penalty_per_hour_usd ?? 0) > 0 ? fmtUsd(Number(s.penalty_per_hour_usd)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Bounded blast radius */}
      {notAffected.length > 0 && (
        <div className="rounded bg-neutral-bg1 border border-border/30 p-2 text-text-secondary">
          <span className="font-semibold text-text-primary">Examined, not affected</span> (bounded blast radius):{" "}
          <span className="font-mono">{notAffected.join(", ")}</span>
        </div>
      )}

      {/* Methodology */}
      {methodology && (
        <div className="text-[10px] text-text-muted leading-relaxed">
          <span className="font-semibold">How this was computed:</span> {methodology}
        </div>
      )}
    </div>
  );
}
