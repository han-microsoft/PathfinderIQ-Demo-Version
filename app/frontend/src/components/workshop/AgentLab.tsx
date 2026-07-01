/**
 * AgentLab — "behind the build" Tab 2: evidence-gated agent-team optimization.
 *
 * Visualises the `agentkit.eval` loop over the REAL telecom-v2 roster:
 *   Case battery (docs → gated cases) │ Iteration timeline (3 team shapes with
 *   the accept-gate verdict) │ Roster → agent spec sheet → tool source.
 *
 * Fully client-side + deterministic (data in agentLabData.ts). The story it
 * tells is the one law: MORE IS NOT BETTER — a bigger team that regressed
 * held-out was reverted; the lean shape that earned its keep was accepted.
 */

import { useEffect, useState } from "react";
import {
  FlaskConical,
  X,
  Code2,
  Check,
  AlertTriangle,
  RotateCcw,
  Wrench,
  Cpu,
  ArrowRight,
  FileText,
} from "lucide-react";
import { useWorkshopStore } from "@/stores/workshopStore";
import { typeColor } from "./OntologyCanvas";
import {
  LAB_TEAMS,
  LAB_AGENTS,
  LAB_TOOLS,
  EVAL_CASES,
  LOOP_STEPS,
  type LabTeam,
  type EvalCase,
  type AgentMeter,
} from "./agentLabData";

/* ── small shared bits ────────────────────────────────────────── */

function VerdictBadge({ verdict }: { verdict: LabTeam["verdict"] }) {
  const map = {
    baseline: { t: "BASELINE", c: "#94a3b8", Icon: FileText },
    reverted: { t: "REVERTED", c: "#f87171", Icon: RotateCcw },
    accepted: { t: "ACCEPTED", c: "#34d399", Icon: Check },
  } as const;
  const { t, c, Icon } = map[verdict];
  return (
    <span
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide"
      style={{ backgroundColor: c + "22", color: c, boxShadow: `inset 0 0 0 1px ${c}55` }}
    >
      <Icon className="h-3 w-3" />
      {t}
    </span>
  );
}

function SignalChip({ signal }: { signal: AgentMeter["signal"] }) {
  const c = signal === "keep" ? "#34d399" : signal === "review" ? "#fbbf24" : "#f87171";
  return (
    <span
      className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide"
      style={{ backgroundColor: c + "22", color: c, boxShadow: `inset 0 0 0 1px ${c}55` }}
    >
      {signal}
    </span>
  );
}

function Meter({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
      <div className="h-full rounded-full" style={{ width: `${Math.round(value * 100)}%`, backgroundColor: color }} />
    </div>
  );
}

/* ── main ─────────────────────────────────────────────────────── */

export function AgentLab() {
  const open = useWorkshopStore((s) => s.labOpen);
  const close = useWorkshopStore((s) => s.closeLab);

  const [teamId, setTeamId] = useState<string>("team-winner");
  const [selectedCase, setSelectedCase] = useState<EvalCase | null>(null);
  const [agentId, setAgentId] = useState<string | null>(null);
  const [toolId, setToolId] = useState<string | null>(null);

  // Escape peels one layer at a time: tool → agent → case → lab.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (toolId) setToolId(null);
      else if (agentId) setAgentId(null);
      else if (selectedCase) setSelectedCase(null);
      else close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, toolId, agentId, selectedCase, close]);

  if (!open) return null;

  const team = LAB_TEAMS.find((t) => t.id === teamId) ?? LAB_TEAMS[0];
  const meterOf = (aid: string) => team.meters.find((m) => m.agentId === aid);
  const heldMax = 80; // scale for the held-out bars
  const agent = agentId ? LAB_AGENTS[agentId] : null;
  const tool = toolId ? LAB_TOOLS[toolId] : null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#0b1220] text-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 px-5 py-3 border-b border-white/10">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🧪</span>
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <FlaskConical className="h-4 w-4 text-sky-300" />
              Agent Lab — Evidence-Gated Team Optimization
            </div>
            <div className="text-xs text-slate-400">
              How the agent team was grown and pruned under one law:{" "}
              <span className="text-sky-300 font-medium">more is not better</span>.
            </div>
          </div>
        </div>
        <button
          onClick={close}
          aria-label="Close Agent Lab"
          className="rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/10"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Loop ribbon */}
      <div className="flex items-stretch gap-1 px-5 py-2 border-b border-white/10 bg-black/20 overflow-x-auto">
        {LOOP_STEPS.map((s, i) => (
          <div key={s.n} className="flex items-center gap-1 shrink-0" title={s.detail}>
            <div className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1">
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-sky-400/20 text-[9px] font-bold text-sky-300">
                {s.n}
              </span>
              <span className="text-[10px] font-medium text-slate-300 whitespace-nowrap">{s.title}</span>
            </div>
            {i < LOOP_STEPS.length - 1 && <ArrowRight className="h-3 w-3 text-slate-600" />}
          </div>
        ))}
      </div>

      {/* Body */}
      <div className="grid flex-1 min-h-0 grid-cols-[300px_minmax(0,1fr)_minmax(0,1fr)]">
        {/* ── Left: case battery ── */}
        <div className="min-h-0 min-w-0 flex flex-col border-r border-white/10">
          <div className="px-4 py-2.5 border-b border-white/10">
            <div className="text-xs font-semibold text-slate-200">Case battery</div>
            <div className="text-[10px] text-slate-500">
              authored from the source documents · 3 gates + train / held-out split
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1.5">
            {EVAL_CASES.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelectedCase(c)}
                className="w-full text-left rounded-lg border border-white/10 bg-white/[0.02] hover:bg-white/[0.06] px-2.5 py-2 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] text-slate-400">{c.id}</span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase"
                    style={
                      c.split === "held_out"
                        ? { backgroundColor: "#fbbf2422", color: "#fbbf24", boxShadow: "inset 0 0 0 1px #fbbf2455" }
                        : { backgroundColor: "#38bdf822", color: "#38bdf8", boxShadow: "inset 0 0 0 1px #38bdf855" }
                    }
                  >
                    {c.split === "held_out" ? "held-out" : "train"}
                  </span>
                </div>
                <div className="mt-0.5 text-[12px] text-slate-200 leading-snug">{c.title}</div>
                <div className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-500">
                  <span className="rounded bg-white/5 px-1 py-0.5">{c.detection.severity}</span>
                  <span className="truncate">{c.source}</span>
                  {c.dataWall && <span className="text-amber-300">· data-wall</span>}
                </div>
              </button>
            ))}
          </div>
          <div className="px-3 py-2 border-t border-white/10 text-[10px] text-slate-500 leading-relaxed">
            <span className="text-slate-400 font-medium">observable</span> = scored ·{" "}
            <span className="text-slate-400 font-medium">hindsight</span> = never scored ·{" "}
            <span className="text-rose-300 font-medium">forbidden</span> = auto-fail. Held-out is
            never tuned against.
          </div>
        </div>

        {/* ── Center: iteration timeline ── */}
        <div className="min-h-0 min-w-0 flex flex-col border-r border-white/10">
          <div className="px-4 py-2.5 border-b border-white/10 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-slate-200">Iteration timeline</div>
              <div className="text-[10px] text-slate-500">held-out operator-quality per team shape</div>
            </div>
            {/* held-out mini bars */}
            <div className="flex items-end gap-2 h-10">
              {LAB_TEAMS.map((t) => {
                const c = t.verdict === "accepted" ? "#34d399" : t.verdict === "reverted" ? "#f87171" : "#94a3b8";
                return (
                  <div key={t.id} className="flex flex-col items-center gap-0.5">
                    <div className="flex h-8 items-end">
                      <div
                        className="w-4 rounded-t"
                        style={{ height: `${(t.gate2Held / heldMax) * 100}%`, backgroundColor: c }}
                        title={`${t.label}: ${t.gate2Held}% held-out`}
                      />
                    </div>
                    <span className="text-[9px] text-slate-500">{t.gate2Held}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3">
            {LAB_TEAMS.map((t) => {
              const active = t.id === teamId;
              const vc = t.verdict === "accepted" ? "#34d399" : t.verdict === "reverted" ? "#f87171" : "#94a3b8";
              return (
                <button
                  key={t.id}
                  onClick={() => {
                    setTeamId(t.id);
                    setAgentId(null);
                  }}
                  className={`w-full text-left rounded-xl border px-3 py-3 transition-colors ${
                    active ? "bg-white/[0.07]" : "bg-white/[0.02] hover:bg-white/[0.05]"
                  }`}
                  style={{ borderColor: active ? vc + "88" : "rgba(255,255,255,0.1)" }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-white/10 text-[10px] font-bold text-slate-300">
                        {t.iteration}
                      </span>
                      <span className="text-sm font-semibold text-white">{t.label}</span>
                    </div>
                    <VerdictBadge verdict={t.verdict} />
                  </div>

                  <div className="mt-1.5 text-[11px] text-slate-400 leading-snug">{t.mutation}</div>

                  {/* metric row */}
                  <div className="mt-2.5 grid grid-cols-4 gap-2 text-center">
                    <Stat label="agents" value={String(t.agentIds.length)} />
                    <Stat label="detect" value={`${t.gate1}%`} />
                    <Stat label="held-out" value={`${t.gate2Held}%`} accent={vc} />
                    <Stat label="cases" value={t.casesHeld} sub="held" />
                  </div>

                  {active && (
                    <>
                      <p className="mt-2.5 text-[11px] text-slate-300 leading-relaxed">{t.note}</p>
                      <div
                        className="mt-2 rounded-lg px-2.5 py-2 text-[11px] leading-relaxed"
                        style={{ backgroundColor: vc + "14", boxShadow: `inset 0 0 0 1px ${vc}44`, color: vc }}
                      >
                        <span className="inline-flex items-center gap-1 font-semibold">
                          {t.verdict === "reverted" ? (
                            <AlertTriangle className="h-3 w-3" />
                          ) : (
                            <Check className="h-3 w-3" />
                          )}
                          accept-gate
                        </span>{" "}
                        <span className="text-slate-300">{t.gateReason}</span>
                      </div>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Right: roster + meters ── */}
        <div className="min-h-0 min-w-0 flex flex-col relative">
          <div className="px-4 py-2.5 border-b border-white/10">
            <div className="text-xs font-semibold text-slate-200">
              {team.label} · roster ({team.agentIds.length} agents)
            </div>
            <div className="text-[10px] text-slate-500">
              agent-weight meter · click an agent for its spec sheet
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2">
            {team.agentIds.map((aid) => {
              const a = LAB_AGENTS[aid];
              const m = meterOf(aid);
              const color = typeColor(a.name);
              return (
                <button
                  key={aid}
                  onClick={() => setAgentId(aid)}
                  className={`w-full text-left rounded-xl border px-3 py-2.5 transition-colors ${
                    a.ablated
                      ? "border-rose-400/30 bg-rose-500/[0.04] hover:bg-rose-500/[0.08]"
                      : "border-white/10 bg-white/[0.02] hover:bg-white/[0.06]"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold"
                      style={{ backgroundColor: color + "22", color, boxShadow: `inset 0 0 0 1px ${color}66` }}
                    >
                      {a.name.replace(/[a-z]/g, "").slice(0, 2)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-[13px] font-semibold ${a.ablated ? "text-rose-200" : "text-white"}`}>
                          {a.name}
                        </span>
                        {m && <SignalChip signal={m.signal} />}
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500">
                        <span className="inline-flex items-center gap-0.5">
                          <Cpu className="h-3 w-3" />
                          {a.model}
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-0.5">
                          <Wrench className="h-3 w-3" />
                          {a.toolIds.length} tools
                        </span>
                        <span>·</span>
                        <span className="truncate">{a.poweredBy}</span>
                      </div>
                    </div>
                  </div>
                  {m && (
                    <div className="mt-2 grid grid-cols-2 gap-3">
                      <div>
                        <div className="flex justify-between text-[9px] text-slate-500">
                          <span>unproductive</span>
                          <span>{Math.round(m.unproductiveRate * 100)}%</span>
                        </div>
                        <Meter value={m.unproductiveRate} color={m.unproductiveRate > 0.5 ? "#f87171" : "#64748b"} />
                      </div>
                      <div>
                        <div className="flex justify-between text-[9px] text-slate-500">
                          <span>gate assoc.</span>
                          <span>{m.gateAssoc.toFixed(2)}</span>
                        </div>
                        <Meter
                          value={Math.max(0, m.gateAssoc)}
                          color={m.gateAssoc <= 0.05 ? "#f87171" : m.gateAssoc < 0.3 ? "#fbbf24" : "#34d399"}
                        />
                      </div>
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Agent spec panel */}
          {agent && (
            <div className="absolute inset-y-0 right-0 z-30 w-[420px] max-w-full flex flex-col border-l border-white/15 bg-[#0f1930] shadow-2xl">
              <div className="flex items-start justify-between gap-2 px-4 py-3 border-b border-white/10">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-white">{agent.name}</div>
                  <div className="flex items-center gap-2 text-[10px] text-slate-400">
                    <span className="inline-flex items-center gap-0.5">
                      <Cpu className="h-3 w-3" />
                      {agent.model}
                    </span>
                    <span>·</span>
                    <span>{agent.poweredBy}</span>
                    {agent.ablated && <span className="text-rose-300 font-semibold">· ablated</span>}
                  </div>
                </div>
                <button
                  onClick={() => setAgentId(null)}
                  aria-label="Close agent"
                  className="rounded p-1 text-slate-400 hover:text-white hover:bg-white/10"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 text-[11px]">
                <div>
                  <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1">Role</div>
                  <p className="text-slate-300 leading-relaxed">{agent.role}</p>
                </div>
                <div>
                  <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1">System prompt</div>
                  <pre className="whitespace-pre-wrap rounded-lg border border-white/10 bg-black/40 p-2.5 text-[10.5px] leading-relaxed text-slate-300 font-mono">
                    {agent.prompt}
                  </pre>
                </div>
                <div>
                  <div className="text-[9px] uppercase tracking-wide text-slate-500 mb-1.5">
                    Tools ({agent.toolIds.length}) · click for source
                  </div>
                  <div className="space-y-1.5">
                    {agent.toolIds.map((tid) => {
                      const tl = LAB_TOOLS[tid];
                      return (
                        <button
                          key={tid}
                          onClick={() => setToolId(tid)}
                          className="w-full text-left rounded-lg border border-white/10 bg-white/[0.03] hover:bg-white/[0.08] px-2.5 py-2 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-sky-300">
                              <Wrench className="h-3 w-3" />
                              {tl.id}
                            </span>
                            <Code2 className="h-3 w-3 text-slate-500" />
                          </div>
                          <div className="mt-0.5 text-[10px] text-slate-400 leading-snug">{tl.summary}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Case detail modal */}
      {selectedCase && (
        <Modal onClose={() => setSelectedCase(null)}>
          <CaseDetail c={selectedCase} />
        </Modal>
      )}

      {/* Tool source modal */}
      {tool && (
        <Modal onClose={() => setToolId(null)} wide>
          <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/10">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-white">
                <Code2 className="h-4 w-4 text-sky-300" />
                <span className="font-mono">{tool.qualified}</span>
              </div>
              <div className="mt-0.5 text-[11px] text-slate-400 leading-snug">{tool.summary}</div>
            </div>
            <button
              onClick={() => setToolId(null)}
              aria-label="Close tool"
              className="shrink-0 rounded p-1 text-slate-400 hover:text-white hover:bg-white/10"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <pre className="flex-1 min-h-0 overflow-auto p-4 text-[11px] leading-relaxed text-slate-300 font-mono">
            {tool.source}
          </pre>
        </Modal>
      )}
    </div>
  );
}

/* ── helpers ──────────────────────────────────────────────────── */

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.04] py-1.5">
      <div className="text-[13px] font-semibold" style={{ color: accent ?? "#e2e8f0" }}>
        {value}
      </div>
      <div className="text-[8.5px] uppercase tracking-wide text-slate-500">
        {label}
        {sub ? ` ${sub}` : ""}
      </div>
    </div>
  );
}

function Modal({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-6" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className={`relative flex max-h-[82vh] w-full flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#0f1930] shadow-2xl ${
          wide ? "max-w-[760px]" : "max-w-[560px]"
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

function GateRow({
  n,
  label,
  color,
  children,
}: {
  n: number;
  label: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <span
          className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold"
          style={{ backgroundColor: color + "22", color }}
        >
          {n}
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color }}>
          {label}
        </span>
      </div>
      <div className="pl-6">{children}</div>
    </div>
  );
}

function Bullets({ items, color }: { items: string[]; color: string }) {
  if (items.length === 0) return <div className="text-[11px] text-slate-600 italic">— none —</div>;
  return (
    <ul className="space-y-0.5">
      {items.map((it, i) => (
        <li key={i} className="flex gap-1.5 text-[11px] text-slate-300 leading-snug">
          <span style={{ color }}>•</span>
          <span>{it}</span>
        </li>
      ))}
    </ul>
  );
}

function CaseDetail({ c }: { c: EvalCase }) {
  return (
    <>
      <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-slate-400">{c.id}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase"
              style={
                c.split === "held_out"
                  ? { backgroundColor: "#fbbf2422", color: "#fbbf24" }
                  : { backgroundColor: "#38bdf822", color: "#38bdf8" }
              }
            >
              {c.split === "held_out" ? "held-out" : "train"}
            </span>
            {c.dataWall && (
              <span className="rounded bg-amber-400/15 px-1.5 py-0.5 text-[9px] font-semibold text-amber-300">
                data-wall · abstention = pass
              </span>
            )}
          </div>
          <div className="mt-0.5 text-sm font-semibold text-white">{c.title}</div>
          <div className="text-[10px] text-slate-500">
            authored from {c.source} · {c.window}
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3.5">
        <GateRow n={1} label="Gate 1 · detection" color="#38bdf8">
          <div className="text-[11px] text-slate-300">
            <span className="font-semibold">{c.detection.event}</span> ·{" "}
            <span className="rounded bg-white/5 px-1 py-0.5">{c.detection.severity}</span>
          </div>
        </GateRow>
        <GateRow n={2} label="Gate 2 · required observable (scored)" color="#34d399">
          <Bullets items={c.observable} color="#34d399" />
        </GateRow>
        <GateRow n={2} label="Gate 2 · bonus hindsight (never scored)" color="#94a3b8">
          <Bullets items={c.hindsight} color="#94a3b8" />
        </GateRow>
        <GateRow n={2} label="Gate 2 · forbidden overreach (auto-fail)" color="#f87171">
          <Bullets items={c.forbidden} color="#f87171" />
        </GateRow>
        <GateRow n={3} label="Gate 3 · reasonable actions" color="#a78bfa">
          <Bullets items={c.actions} color="#a78bfa" />
        </GateRow>
      </div>
    </>
  );
}
