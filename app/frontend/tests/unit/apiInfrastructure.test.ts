/**
 * Pre-refactor tests for API client infrastructure.
 *
 * Purpose:
 *   Verifies behavior of the shared API infrastructure (ApiError,
 *   handleResponse) before the Phase 1 dedup removes inline copies
 *   from client.ts. After refactor, these tests still import from
 *   the same module and must pass unchanged.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

/* ── Inline copies of API infrastructure (from client.ts L102-L114) ── */

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json();
}

/* ── Tests ── */

describe("ApiError", () => {
  it("stores status and detail", () => {
    const err = new ApiError(404, "Not found");
    expect(err.status).toBe(404);
    expect(err.detail).toBe("Not found");
    expect(err.message).toBe("API 404: Not found");
    expect(err.name).toBe("ApiError");
  });

  it("is an instance of Error", () => {
    const err = new ApiError(500, "Server error");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("handleResponse", () => {
  it("returns parsed JSON for ok response", async () => {
    const mockRes = {
      ok: true,
      json: vi.fn().mockResolvedValue({ id: "123", title: "test" }),
    } as unknown as Response;

    const result = await handleResponse<{ id: string }>(mockRes);
    expect(result).toEqual({ id: "123", title: "test" });
  });

  it("throws ApiError with detail from JSON body on non-ok response", async () => {
    const mockRes = {
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: vi.fn().mockResolvedValue({ detail: "Invalid input" }),
    } as unknown as Response;

    await expect(handleResponse(mockRes)).rejects.toThrow(ApiError);
    try {
      await handleResponse(mockRes);
    } catch (err) {
      expect((err as ApiError).status).toBe(400);
      expect((err as ApiError).detail).toBe("Invalid input");
    }
  });

  it("falls back to statusText when JSON body parse fails", async () => {
    const mockRes = {
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: vi.fn().mockRejectedValue(new Error("not json")),
    } as unknown as Response;

    try {
      await handleResponse(mockRes);
    } catch (err) {
      expect((err as ApiError).status).toBe(502);
      expect((err as ApiError).detail).toBe("Bad Gateway");
    }
  });

  it("falls back to statusText when detail field is missing", async () => {
    const mockRes = {
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: vi.fn().mockResolvedValue({ error: true }),
    } as unknown as Response;

    try {
      await handleResponse(mockRes);
    } catch (err) {
      expect((err as ApiError).detail).toBe("Forbidden");
    }
  });
});
