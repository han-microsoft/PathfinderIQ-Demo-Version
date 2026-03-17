/**
 * Platform API — feedback, preferences, and other platform calls.
 *
 * Extracted from client.ts for domain-specific organization.
 */

import { BASE, authHeaders, handleResponse } from "./client";

export async function submitFeedback(
  title: string,
  description: string,
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${BASE}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify({ title, description }),
  });
  return handleResponse<{ id: string; status: string }>(res);
}

export interface UserPreferences {
  scenario_name: string;
}

export async function getPreferences(): Promise<UserPreferences> {
  const res = await fetch(`${BASE}/preferences`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<UserPreferences>(res);
}

/** Fetch observability status (last agent run, breaker states). */
export async function getObservabilityStatus(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/observability/status`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Record<string, unknown>>(res);
}

/** Fetch service health (all dependency checks). */
export async function getServiceHealth(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/services/health`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Record<string, unknown>>(res);
}
