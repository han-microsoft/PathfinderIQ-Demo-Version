/**
 * SessionMetrics — token counts, tool calls, duration, TTFT/TTLT, fabric state.
 *
 * Consumes chatStore and observabilityStore via Zustand selectors.
 */

import { useEffect } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import { useObservabilityStore } from "@/stores/observabilityStore";
import { MetricRow } from "./MetricRow";
import { useTranslation } from "@/hooks/useTranslation";

/** Polling interval for observability status (ms). */
const POLL_INTERVAL = 5_000;

/** Stats data shape passed into the metrics display. */
export interface StatsData {
  model: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  durationMs: number;
  threadId: string | null;
  toolCalls: number | null;
}

export function SessionMetrics({ showHeader = true }: { showHeader?: boolean }) {
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const lastMeta = useChatStore((s) => s.getSlice(activeAgentId).lastMetadata);
  const { status, fetchStatus } = useObservabilityStore();
  const { t } = useTranslation();

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, POLL_INTERVAL);
    return () => clearInterval(id);
  }, [fetchStatus]);

  /* Merge: prefer real-time chatStore data, fall back to polled status */
  const statsData: StatsData | null = lastMeta
    ? {
        model: lastMeta.model || "—",
        inputTokens: lastMeta.prompt_tokens,
        outputTokens: lastMeta.completion_tokens,
        totalTokens: lastMeta.total_tokens,
        durationMs: lastMeta.duration_ms,
        threadId: null,
        toolCalls: null,
      }
    : status
      ? {
          model: status.last_run.model || "—",
          inputTokens: status.last_run.input_tokens,
          outputTokens: status.last_run.output_tokens,
          totalTokens: status.last_run.total_tokens,
          durationMs: status.last_run.duration_ms,
          threadId: status.last_run.thread_id || null,
          toolCalls: status.last_run.tool_calls,
        }
      : null;

  const fabricStatus = status?.fabric ?? null;
  const toolCallsFromStatus = status?.last_run.tool_calls ?? null;

  return (
    <>
      {showHeader && (
        <div className="flex items-center justify-between border-b border-border bg-header-bg px-4 py-1.5 shrink-0">
          <h2 className="text-[19px] font-semibold text-header-text uppercase tracking-wider">
            {t("metrics.sessionMetrics")}
          </h2>
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <SessionMetricsContent
          stats={statsData}
          fabricStatus={fabricStatus}
          toolCallsFromStatus={toolCallsFromStatus}
        />
      </div>
    </>
  );
}

/** Inner content — renders all metric rows. */
function SessionMetricsContent({
  stats,
  fabricStatus,
  toolCallsFromStatus,
}: {
  stats: StatsData | null;
  fabricStatus: {
    state: string;
    consecutive_429s: number;
    cooldown_s: number;
    semaphore_available: number;
  } | null;
  toolCallsFromStatus: number | null;
}) {
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const messages = useChatStore((s) => s.getSlice(activeAgentId).messages);
  const ttftMs = useChatStore((s) => s.getSlice(activeAgentId).ttftMs);
  const ttltMs = useChatStore((s) => s.getSlice(activeAgentId).ttltMs);
  const ttftHistory = useChatStore((s) => s.getSlice(activeAgentId).ttftHistory);
  const ttltHistory = useChatStore((s) => s.getSlice(activeAgentId).ttltHistory);
  const { t } = useTranslation();

  if (!stats) {
    return (
      <p className="text-[19px] text-text-muted text-center py-2">
        {t("metrics.noData")}
      </p>
    );
  }

  const userMsgCount = messages.filter((m) => m.role === "user").length;
  const agentMsgCount = messages.filter((m) => m.role === "assistant").length;
  const toolCalls = toolCallsFromStatus ?? stats.toolCalls ?? 0;
  const avgTokensPerPrompt = userMsgCount > 0 ? Math.round(stats.inputTokens / userMsgCount) : 0;
  const avgTokensPerResponse = agentMsgCount > 0 ? Math.round(stats.outputTokens / agentMsgCount) : 0;
  const avgTtft = ttftHistory.length > 0 ? Math.round(ttftHistory.reduce((a, b) => a + b, 0) / ttftHistory.length) : null;
  const avgTtlt = ttltHistory.length > 0 ? Math.round(ttltHistory.reduce((a, b) => a + b, 0) / ttltHistory.length) : null;

  return (
    <div className="space-y-1">
      <div className="text-[16px] uppercase tracking-wider text-text-muted font-semibold pt-1">{t("metrics.tokens")}</div>
      <div className="border-t border-border/30 mb-1" />
      <MetricRow label={t("metrics.in")} value={stats.inputTokens} />
      <MetricRow label={t("metrics.out")} value={stats.outputTokens} />
      <MetricRow label={t("metrics.total")} value={stats.totalTokens} color="text-brand" />

      <div className="border-t border-border/30 my-1.5" />
      <MetricRow label={t("metrics.toolCalls")} value={toolCalls} color="text-status-warning" />
      <MetricRow label={t("metrics.userMessages")} value={userMsgCount} />
      <MetricRow label={t("metrics.duration")} value={`${(stats.durationMs / 1000).toFixed(1)}s`} color="text-status-info" />

      <div className="border-t border-border/30 my-1.5" />
      <MetricRow label={t("metrics.avgTokensPrompt")} value={avgTokensPerPrompt} />
      <MetricRow label={t("metrics.avgTokensResponse")} value={avgTokensPerResponse} />
      <MetricRow label={t("metrics.avgTtft")} value={avgTtft != null ? `${(avgTtft / 1000).toFixed(1)}s` : "—"} color="text-status-info" />
      <MetricRow label={t("metrics.avgTtlt")} value={avgTtlt != null ? `${(avgTtlt / 1000).toFixed(1)}s` : "—"} color="text-status-info" />

      {(ttftMs != null || ttltMs != null) && (
        <>
          <div className="border-t border-border/30 my-1.5" />
          {ttftMs != null && <MetricRow label={t("metrics.lastTtft")} value={`${(ttftMs / 1000).toFixed(2)}s`} />}
          {ttltMs != null && <MetricRow label={t("metrics.lastTtlt")} value={`${(ttltMs / 1000).toFixed(1)}s`} />}
        </>
      )}

      {fabricStatus && fabricStatus.state !== "closed" && (
        <>
          <div className="border-t border-border/30 my-1.5" />
          <MetricRow label={t("metrics.fabric")} value={fabricStatus.state} color="text-status-error" />
          {fabricStatus.consecutive_429s > 0 && (
            <MetricRow label={t("metrics.rateLimits")} value={fabricStatus.consecutive_429s} color="text-status-error" />
          )}
        </>
      )}
    </div>
  );
}
