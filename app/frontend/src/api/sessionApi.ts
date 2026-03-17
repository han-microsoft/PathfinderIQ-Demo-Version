/**
 * Session API — CRUD operations for chat sessions.
 *
 * Extracted from client.ts for domain-specific organization.
 * All session-related HTTP calls live here.
 */

import type {
  CreateSessionRequest,
  Message,
  Session,
  SessionSummary,
  UpdateSessionRequest,
} from "./types";
import { BASE, authHeaders, handleResponse, ApiError } from "./client";

export async function createSession(
  req?: CreateSessionRequest,
): Promise<Session> {
  const res = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify(req ?? {}),
  });
  return handleResponse<Session>(res);
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${BASE}/sessions`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<SessionSummary[]>(res);
}

export async function getSession(sessionId: string): Promise<Session> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Session>(res);
}

export async function updateSession(
  sessionId: string,
  req: UpdateSessionRequest,
): Promise<Session> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...await authHeaders() },
    body: JSON.stringify(req),
  });
  return handleResponse<Session>(res);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { ...await authHeaders() },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
}

export async function saveSession(
  sessionId: string,
): Promise<{ status: string; path: string }> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/save`, {
    method: "POST",
    headers: { ...await authHeaders() },
  });
  return handleResponse<{ status: string; path: string }>(res);
}

export async function loadSavedSessions(): Promise<{
  loaded: number;
  errors: number;
}> {
  const res = await fetch(`${BASE}/sessions/load-saved`, {
    method: "POST",
    headers: { ...await authHeaders() },
  });
  return handleResponse<{ loaded: number; errors: number }>(res);
}

export async function resetDefaults(): Promise<{
  deleted: number;
  seeded: number;
}> {
  const res = await fetch(`${BASE}/sessions/reset-defaults`, {
    method: "POST",
    headers: { ...await authHeaders() },
  });
  return handleResponse<{ deleted: number; seeded: number }>(res);
}

export async function getThreadMessages(
  sessionId: string,
  threadId: string,
): Promise<Message[]> {
  const res = await fetch(`${BASE}/sessions/${sessionId}/thread/${threadId}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Message[]>(res);
}
