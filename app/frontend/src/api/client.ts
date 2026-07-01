/**
 * API client — typed fetch helpers + SSE streaming.
 *
 * Module role:
 *   The only module that makes HTTP requests to the backend. All API access
 *   goes through these exported functions. Provides:
 *     - Typed CRUD operations for session management
 *     - SSE streaming via fetch + ReadableStream (not EventSource)
 *     - AbortController support for user-initiated cancellation
 *
 * Design decisions:
 *   - All methods return typed responses or throw ApiError
 *   - Uses fetch + ReadableStream instead of EventSource because:
 *     (a) EventSource is GET-only; our chat endpoint requires POST
 *     (b) No native abort signal support in EventSource
 *     (c) Custom SSE event type parsing needed
 *   - Base URL from VITE_API_URL env var:
 *     dev:  http://localhost:9000/api (CORS handles cross-origin)
 *     prod: /api (same origin behind reverse proxy)
 *
 * Key collaborators:
 *   - api/types.ts           — all request/response types
 *   - stores/sessionStore.ts — calls session CRUD functions
 *   - stores/chatStore.ts    — calls streamChat for SSE streaming
 *
 * Dependents:
 *   Called by: sessionStore.ts, chatStore.ts exclusively
 */

import { getAccessToken } from "../auth";
import { BASE } from "@/foundation/constants";
import { msalInstance, authSetup } from "../auth/authConfig";

export { BASE };

// ── Auth session recovery ──────────────────────────────────────────────────

/**
 * Handle a 401 response by redirecting to the Entra login page.
 *
 * When the backend returns 401, the access token has expired and silent/popup
 * renewal already failed (getAccessToken tried both). Redirect the user to
 * the Entra login page so they can re-authenticate. After login, MSAL
 * redirects back to the app and restores the session.
 */
export function handleAuthExpired(): void {
  if (!msalInstance || !authSetup.useLogin) return;
  console.warn("[auth] Session expired — redirecting to login");
  msalInstance.loginRedirect({ scopes: authSetup.scopes ?? [] }).catch((err) => {
    console.error("[auth] loginRedirect failed:", err);
  });
}

// ── Auth + Context Headers ──────────────────────────────────────────────────

/**
 * Build auth + per-user scenario headers for API requests.
 *
 * Attaches:
 *   - Authorization: Bearer <token>  (when auth enabled)
 *   - X-Scenario-Name: <active scenario>  (per-user isolation)
 *
 * Scenario is the only user-owned runtime selector. The backend resolves
 * the effective graph backend and model from scenario + operator config.
 */
export async function authHeaders(): Promise<HeadersInit> {
  const headers: Record<string, string> = {};

  // Auth token
  const token = await getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  // User language — backend uses this to inject response-language instructions
  // into agent prompts. Imported dynamically to avoid circular init deps.
  try {
    const { useLocaleStore } = await import("@/stores/localeStore");
    headers["X-User-Language"] = useLocaleStore.getState().locale;
  } catch { /* locale store not yet initialised — default to en */ }

  // Active scenario — backend resolves agents/prompts/tools/datasource/topology
  // per-request from this header (validated against the on-disk pack allowlist).
  try {
    const { useScenarioStore } = await import("@/stores/scenarioStore");
    const scenario = useScenarioStore.getState().selectedScenario;
    if (scenario) headers["X-Scenario-Name"] = scenario;
  } catch { /* scenario store not yet initialised — backend uses operator default */ }

  return headers;
}

// ── Error ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) {
      handleAuthExpired();
    }
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

// ── Barrel re-exports ───────────────────────────────────────────────────────
// Domain-specific API files. All endpoint functions live in their domain file.
// This barrel re-exports them so `import * as api from "@/api/client"` works.
export * from "./sessionApi";
export * from "./chatApi";
export * from "./scenarioApi";
export * from "./platformApi";
