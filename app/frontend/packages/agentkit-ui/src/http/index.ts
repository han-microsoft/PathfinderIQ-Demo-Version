/**
 * agentkit-ui / http — domain-blind HTTP helpers for a JSON+SSE backend.
 *
 * Pure, framework-agnostic pieces shared by every API consumer:
 *   - ApiError            typed error carrying status + detail
 *   - extractErrorMessage shape-tolerant detail parser (`{detail}` string
 *                         OR `{detail:{message}}` envelope)
 *   - parseResponse       status-check + JSON parse, with an injectable
 *                         `onUnauthorized` hook (the auth SDK stays the
 *                         consumer's concern — never hardcode MSAL here)
 *   - buildBearerHeaders  `Authorization: Bearer <token>` builder
 *
 * The consumer composes these with its own auth + dev-identity logic.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/**
 * Read a human-readable error message from a backend response body.
 * Accepts both `{detail: "<string>"}` and `{detail: {message, ...}}`.
 */
export function extractErrorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
  }
  return fallback;
}

export interface ParseResponseOptions {
  /** Invoked on a 401 before throwing — e.g. trigger a login redirect. */
  onUnauthorized?: () => void;
}

/**
 * Status-check + JSON-parse a fetch Response. Throws `ApiError` on non-2xx
 * (after firing `onUnauthorized` on 401). Returns the parsed JSON otherwise.
 */
export async function parseResponse<T>(
  res: Response,
  options: ParseResponseOptions = {},
): Promise<T> {
  if (!res.ok) {
    if (res.status === 401) options.onUnauthorized?.();
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, extractErrorMessage(body, res.statusText));
  }
  return res.json() as Promise<T>;
}

/**
 * Build `Authorization: Bearer <token>` headers from an async token getter.
 * Returns an empty object when the getter yields no token (the consumer adds
 * its own unauthenticated/dev-identity fallback).
 */
export async function buildBearerHeaders(
  getToken: () => Promise<string | null | undefined>,
): Promise<Record<string, string>> {
  const token = await getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
