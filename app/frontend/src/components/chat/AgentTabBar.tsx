/**
 * AgentTabBar — horizontal tab bar for switching between agent chat tabs.
 *
 * Renders one tab per agent from the agentStore. The active tab is
 * highlighted with a brand-colored bottom border. Each tab shows the
 * agent's display name.
 *
 * Key collaborators:
 *   - stores/agentStore.ts  — agents array, activeAgentId, setActiveAgent
 *
 * Dependents:
 *   Rendered by ChatPanel above the MessageList.
 */

import { useEffect, useMemo, useState } from "react";
import type { MouseEvent } from "react";
import { Info, X } from "lucide-react";
import type { AgentInfo } from "@/api/types";
import { useAgentStore } from "@/stores/agentStore";
import { getAgentFullBody, getAgentHeadshot } from "@/utils/agentHeadshots";
import { useTranslation } from "@/hooks/useTranslation";

function toTitleCase(value: string): string {
  return value
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getCapabilities(tools: string[], t: (key: string) => string): string[] {
  const capabilityByNamespace: Record<string, string> = {
    delegation: t("agent.capability.delegation"),
    dispatch: t("agent.capability.dispatch"),
    email: t("agent.capability.communications"),
    graph_explorer: t("agent.capability.graphAnalysis"),
    incidents: t("agent.capability.incidentResponse"),
    network: "Network diagnostics",
    search: t("agent.capability.knowledgeRetrieval"),
    telemetry: t("agent.capability.telemetryAnalysis"),
    thinking: t("agent.capability.reasoning"),
  };

  return Array.from(
    new Set(
      tools
        .map((tool) => tool.split(":")[0]?.split(".").pop() ?? "")
        .filter(Boolean)
        .map((namespace) => capabilityByNamespace[namespace] ?? toTitleCase(namespace)),
    ),
  );
}

function formatToolLabel(tool: string, t?: (key: string) => string): string {
  const [, fn = tool] = tool.split(":");
  // Check locale-specific tool name override
  if (t) {
    const localeKey = `tool.name.${fn}`;
    const localeVal = t(localeKey);
    if (localeVal !== localeKey) return localeVal;
  }
  return toTitleCase(fn);
}

function normalizeAgentKey(value: string): string {
  return value.replace(/[-_\s]/g, "").toLowerCase();
}

function getProductSummary(agent: AgentInfo, t: (key: string) => string): string {
  // Check locale-specific override first (keyed by agent ID)
  const localeKey = `agent.product.${agent.id}`;
  const localeVal = t(localeKey);
  if (localeVal !== localeKey) return localeVal;

  if (agent.product_summary?.trim()) {
    return agent.product_summary;
  }

  const key = normalizeAgentKey(agent.name || agent.id);
  const byAgent: Record<string, string> = {
    nocorchestrator:
      "Uses Microsoft Foundry to orchestrate agent tooling and help build robust multi-agent systems end-to-end.",
    networkinvestigator:
      "Uses Fabric IQ for graph traversal (GQL) to trace topology dependencies, and Fabric Eventhouse (KQL) for real-time telemetry and per-sensor fault localization.",
    fieldcoordinator:
      "Uses Fabric IQ to build and traverse the operational graph, running GQL queries to find assets, relationships, and field context quickly.",
    knowledgeanalyst:
      "Uses Foundry IQ for advanced vector search to retrieve relevant information from large unstructured sources such as procedures and policy documents.",
    communicationsspecialist:
      "Uses Microsoft Foundry tool calling to generate incident tickets, customer advisories, and stakeholder reports from a single synthesis. WorkIQ envisioned for direct interface with communications platforms, tools, and foundational datasources.",
  };

  return byAgent[key] || t("agent.noProductDetails");
}

/** Stack icons for each agent — which Microsoft products they use. */
function getStackIcons(agent: AgentInfo): { src: string; label: string }[] {
  if (agent.powered_by?.length) {
    return agent.powered_by.map((entry) => ({ src: entry.logo_url, label: entry.label }));
  }

  const key = normalizeAgentKey(agent.name || agent.id);
  const byAgent: Record<string, { src: string; label: string }[]> = {
    nocorchestrator: [
      { src: "/images/foundryiq-logo.png", label: "Azure AI Foundry" },
    ],
    networkinvestigator: [
      { src: "/images/fabric-logo.png", label: "Fabric IQ (GQL + KQL)" },
    ],
    fieldcoordinator: [
      { src: "/images/fabric-logo.png", label: "Fabric IQ (GQL)" },
      { src: "/images/azureaisearch.png", label: "Azure AI Search" },
    ],
    knowledgeanalyst: [
      { src: "/images/foundryiq-logo.png", label: "Foundry IQ" },
      { src: "/images/azureaisearch.png", label: "Azure AI Search" },
    ],
    communicationsspecialist: [
      { src: "/images/foundryiq-logo.png", label: "Azure AI Foundry" },
      { src: "/images/copilot-logo.png", label: "WorkIQ (envisioned)" },
    ],
  };
  return byAgent[key] ?? [];
}

export function AgentTabBar() {
  const agents = useAgentStore((s) => s.agents);
  const activeAgentId = useAgentStore((s) => s.activeAgentId);
  const setActiveAgent = useAgentStore((s) => s.setActiveAgent);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);
  const { t } = useTranslation();
  const selectedAgentFullBody = selectedAgent
    ? (selectedAgent.full_body_url ?? getAgentFullBody(selectedAgent.name) ?? undefined)
    : undefined;

  const selectedCapabilities = useMemo(
    () => getCapabilities(selectedAgent?.tools ?? [], t),
    [selectedAgent, t],
  );

  useEffect(() => {
    if (!selectedAgent) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelectedAgent(null);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedAgent]);

  const handleTabClick = (event: MouseEvent<HTMLButtonElement>, agent: AgentInfo) => {
    const target = event.target as HTMLElement;
    const clickedInfo = target.closest("[data-info-trigger='true']");
    if (clickedInfo) {
      event.preventDefault();
      setSelectedAgent(agent);
      return;
    }
    setActiveAgent(agent.id);
  };

  /* Don't render the tab bar if there are 0 or 1 agents. */
  if (agents.length <= 1) return null;

  return (
    <>
      <div className="flex border-b border-border bg-header-bg shrink-0 overflow-x-auto">
        {agents.map((agent) => {
          const isActive = agent.id === activeAgentId;
          const headshotSrc = agent.headshot_url ?? getAgentHeadshot(agent.name) ?? undefined;
          return (
            <button
              key={agent.id}
              onClick={(event) => handleTabClick(event, agent)}
              className={`
              px-4 py-2 text-xs font-medium whitespace-nowrap transition-colors
              border-b-2 flex items-center gap-2
              ${isActive
                ? "border-brand text-brand bg-neutral-bg1"
                : "border-transparent text-header-text/60 hover:text-header-text hover:bg-header-bg/80"
              }
            `}
              title={agent.description}
            >
              <img
                src={headshotSrc}
                alt=""
                className="h-10 w-10 rounded-full object-cover shrink-0"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
              {t(`agent.name.${agent.id}`) !== `agent.name.${agent.id}` ? t(`agent.name.${agent.id}`) : agent.name}
              <span
                data-info-trigger="true"
                className="ml-0.5 inline-flex items-center justify-center rounded-full border border-current/30 p-0.5 text-current/75 opacity-85 transition-all hover:scale-110 hover:bg-current/15 hover:text-current hover:opacity-100 cursor-pointer"
                title={`View ${agent.name} details`}
                aria-label={`View ${agent.name} details`}
              >
                <Info data-info-trigger="true" className="h-3.5 w-3.5 stroke-[2.4]" />
              </span>
            </button>
          );
        })}
      </div>

      {selectedAgent && (
        <div
          className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          onClick={() => setSelectedAgent(null)}
          role="dialog"
          aria-modal="true"
          aria-label={`${t(`agent.name.${selectedAgent.id}`) !== `agent.name.${selectedAgent.id}` ? t(`agent.name.${selectedAgent.id}`) : selectedAgent.name} details`}
        >
          <div
            className="bg-neutral-bg2 border border-border rounded-xl shadow-2xl w-[min(520px,92vw)] max-h-[85vh] overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h3 className="text-lg font-semibold text-text-primary">{t(`agent.name.${selectedAgent.id}`) !== `agent.name.${selectedAgent.id}` ? t(`agent.name.${selectedAgent.id}`) : selectedAgent.name}</h3>
              <button
                type="button"
                onClick={() => setSelectedAgent(null)}
                className="text-text-muted hover:text-text-primary"
                aria-label={t("common.close")}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 overflow-y-auto max-h-[calc(85vh-64px)] space-y-4 text-sm text-text-secondary">
              {/* Agent image — top, centered */}
              <div className="flex justify-center rounded-lg bg-neutral-bg3 border border-border p-3">
                <img
                  src={selectedAgentFullBody}
                  alt={`${selectedAgent.name} full body`}
                  className="max-h-[280px] w-auto object-contain"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{t("agent.description")}</h4>
                <p>{t(`agent.desc.${selectedAgent.id}`) !== `agent.desc.${selectedAgent.id}` ? t(`agent.desc.${selectedAgent.id}`) : (selectedAgent.description || t("agent.noDescription"))}</p>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{t("agent.product")}</h4>
                <p>{getProductSummary(selectedAgent, t)}</p>
              </div>

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{t("agent.capabilities")}</h4>
                {selectedCapabilities.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {selectedCapabilities.map((capability) => (
                      <span
                        key={capability}
                        className="text-xs px-2 py-1 rounded-md border border-border bg-neutral-bg3 text-text-primary"
                      >
                        {capability}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p>{t("agent.noCapabilities")}</p>
                )}
              </div>

              {/* Stack icons — which Microsoft products this agent uses */}
              {getStackIcons(selectedAgent).length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{t("agent.poweredBy")}</h4>
                  <div className="flex flex-wrap gap-3">
                    {getStackIcons(selectedAgent).map((icon) => (
                      <div key={icon.label} className="flex items-center gap-2 rounded-lg border border-border bg-neutral-bg3 px-3 py-1.5">
                        <img src={icon.src} alt="" className="h-6 w-6 shrink-0 object-contain" />
                        <span className="text-xs text-text-primary">{icon.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">{t("agent.tools")}</h4>
                {selectedAgent.tools.length > 0 ? (
                  <ul className="space-y-1 list-disc list-inside">
                    {selectedAgent.tools.map((tool) => (
                      <li key={tool} className="text-text-secondary">
                        <span className="text-text-primary">{formatToolLabel(tool, t)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>{t("agent.noTools")}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
