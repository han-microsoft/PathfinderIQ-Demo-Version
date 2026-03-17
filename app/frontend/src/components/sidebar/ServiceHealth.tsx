/**
 * ServiceHealth — live connectivity indicators for Azure services.
 *
 * Polls ``GET /api/services/health`` every 45s on mount, with a manual
 * sync button. Shows each service with a colored status dot + label,
 * and nested sub-resources (indexes, models, ontology, database).
 */

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "@/hooks/useTranslation";

/**
 * Shape of a single service from the backend response.
 *
 * Status values match the backend ``DependencyStatus`` enum:
 *   up, down, degraded, throttled, not_configured.
 * Legacy values (connected/disconnected/awaiting) are also accepted
 * for backwards compatibility with the old router_service_health.py.
 */
interface ServiceStatus {
  status: "up" | "down" | "degraded" | "throttled" | "not_configured"
        | "connected" | "disconnected" | "awaiting";
  endpoint?: string | null;
  error?: string;
  // Sub-resources (varies by service)
  indexes?: string[];
  models?: string[];
  resources?: string[];
  workspace?: string | null;
  database?: string | null;
  type?: string;
  provider?: string;
}

/** Full response from GET /api/services/health. */
interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: Record<string, ServiceStatus>;
  circuit_breakers?: Record<string, unknown>;
  cache_ttl_seconds?: number;
}

/** Polling interval (ms) — 5 minutes. */
const POLL_INTERVAL = 300_000;

/** Display config for each service. */
const SERVICE_META: Record<
  string,
  { label: string; icon: string; subKey: string }
> = {
  ai_search: { label: "Azure AI Search", icon: "/images/azure-logo.png", subKey: "indexes" },
  ai_foundry: { label: "AI Foundry", icon: "/images/foundry-logo.png", subKey: "models" },
  fabric: { label: "Microsoft Fabric", icon: "/images/fabric-logo.png", subKey: "resources" },
  cosmos_sessions: { label: "Cosmos DB", icon: "/images/cosmosdb-logo.png", subKey: "database" },
  session_store: { label: "Session Store", icon: "/images/memory-icon.png", subKey: "database" },
};

export function ServiceHealth({ showHeader = true }: { showHeader?: boolean }) {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const { t } = useTranslation();

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const { getServiceHealth } = await import("@/api/platformApi");
      const data = await getServiceHealth() as unknown as HealthResponse;
      setData(data);
    } catch {
      /* Fail silent — keep last known state */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, POLL_INTERVAL);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="shrink-0">
      {showHeader && (
        <>
          <div className="flex items-center justify-between border-border bg-header-bg px-4 py-1.5">
            <h2 className="text-sm font-semibold text-header-text uppercase tracking-wider">
              {t("health.serviceHealth")}
            </h2>
            <button
              onClick={fetchHealth}
              disabled={loading}
              className="text-text-muted hover:text-brand transition-colors disabled:opacity-40"
              title={t("health.refresh")}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
          <div className="flex items-center justify-between border-b border-border px-4 py-1.5">
            <p className="text-xs text-text-muted italic leading-snug text-left">
              {t("health.pingInterval")}
            </p>
          </div>
        </>
      )}
      {!showHeader && (
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-text-muted italic">{t("health.pingShort")}</p>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="text-text-muted hover:text-brand transition-colors disabled:opacity-40"
            title={t("health.refresh")}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      )}
      <div className="px-3 py-1.5 space-y-1.5">
        {data ? (
          Object.entries(SERVICE_META).map(([key, meta]) => {
            const svc = (data.services as Record<string, ServiceStatus>)[key];
            if (!svc) return null;
            return (
              <ServiceCard key={key} meta={meta} svc={svc} />
            );
          })
        ) : (
          <p className="text-sm text-text-muted text-center py-4">
            {t("health.checking")}
          </p>
        )}
      </div>
    </div>
  );
}

/** Single service card with status dot, label, and nested sub-resources. */
function ServiceCard({
  meta,
  svc,
}: {
  meta: { label: string; icon: string; subKey: string };
  svc: ServiceStatus;
}) {
  // Map backend DependencyStatus enum values to display properties.
  // "up"/"connected" → green, "degraded"/"throttled"/"awaiting" → amber,
  // "not_configured" → muted, "down"/"disconnected" → red.
  const isUp = svc.status === "up" || svc.status === "connected";
  const isWarn = svc.status === "degraded" || svc.status === "throttled" || svc.status === "awaiting";
  const isNotConfigured = svc.status === "not_configured";

  const statusColor = isUp
    ? "text-status-success"
    : isWarn
      ? "text-status-warning"
      : isNotConfigured
        ? "text-text-muted"
        : "text-status-error";
  const dotColor = isUp
    ? "bg-status-success"
    : isWarn
      ? "bg-status-warning"
      : isNotConfigured
        ? "bg-text-muted/40"
        : "bg-status-error";

  const { t } = useTranslation();
  const STATUS_LABELS: Record<string, string> = {
    up: t("health.connected"),
    connected: t("health.connected"),
    degraded: t("health.degraded"),
    throttled: t("health.throttled"),
    not_configured: t("health.notConfigured"),
    awaiting: t("health.awaiting"),
    down: t("health.disconnected"),
    disconnected: t("health.disconnected"),
  };
  const statusLabel = STATUS_LABELS[svc.status] ?? t("health.disconnected");

  // Collect sub-resources
  const subItems: string[] = [];
  if (meta.subKey === "indexes" && svc.indexes) subItems.push(...svc.indexes);
  if (meta.subKey === "models" && svc.models) subItems.push(...svc.models);
  if (meta.subKey === "resources" && svc.resources) subItems.push(...svc.resources);
  if (meta.subKey === "database" && svc.database) subItems.push(svc.database);
  if (meta.subKey === "provider" && svc.provider) subItems.push(svc.provider);

  return (
    <div className="rounded-md bg-neutral-bg3/40 px-2.5 py-1.5">
      {/* Service header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
          <span className="text-sm font-medium text-text-primary flex items-center gap-1.5">
            <img src={meta.icon} alt="" className="h-4 w-4 shrink-0" />
            {meta.label}
          </span>
        </div>
        <span className={`text-xs font-semibold ${statusColor}`}>
          {statusLabel}
        </span>
      </div>

      {/* Sub-resources */}
      {subItems.length > 0 && (
        <div className="ml-5 mt-0.5 space-y-0">
          {subItems.map((item, i) => (
            <div key={i} className="flex items-center gap-1.5 text-xs text-text-muted font-mono">
              <span className="text-text-muted/50">•</span>
              <span className="truncate">{item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
