import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/auth", () => ({
  getAccessToken: vi.fn().mockResolvedValue("test-token"),
}));

vi.mock("@/stores/scenarioStore", () => ({
  useScenarioStore: {
    getState: () => ({
      items: [{ name: "telecom-playground-v2", is_active: true }],
      _activeOverride: "",
    }),
  },
}));

describe("authHeaders", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("sends authorization and scenario headers only", async () => {
    const { authHeaders } = await import("@/api/client");

    const headers = await authHeaders() as Record<string, string>;

    expect(headers.Authorization).toBe("Bearer test-token");
    expect(headers["X-Scenario-Name"]).toBe("telecom-playground-v2");
    expect(headers["X-Graph-Backend"]).toBeUndefined();
    expect(headers["X-LLM-Model"]).toBeUndefined();
  });
});