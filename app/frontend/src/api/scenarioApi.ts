/**
 * Scenario API — scenario and scenario-scoped metadata calls.
 *
 * Extracted from client.ts for domain-specific organization.
 */

import type {
  AgentInfo,
  ScenarioDetail,
} from "./types";
import { BASE, authHeaders, handleResponse } from "./client";

/** Fetch agent definitions from the scenario's agent config. */
export async function getAgents(): Promise<AgentInfo[]> {
  const res = await fetch(`${BASE}/agents/`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<AgentInfo[]>(res);
}

/** Fetch the active scenario's detail metadata (display_name, examples, demo_flows). */
export async function getScenarioDetail(): Promise<ScenarioDetail> {
  const res = await fetch(`${BASE}/scenario`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<ScenarioDetail>(res);
}

/** Fetch the active scenario's graph topology data. */
export async function getTopology(signal?: AbortSignal): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/scenario/topology`, {
    headers: { ...await authHeaders() },
    signal,
  });
  return handleResponse<Record<string, unknown>>(res);
}

/** Fetch the full assembled prompt text for an agent. */
export async function getAgentPrompt(agentId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/scenario/agent-prompt?agent_id=${encodeURIComponent(agentId)}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Record<string, unknown>>(res);
}
