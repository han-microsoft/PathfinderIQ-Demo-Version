import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/stores/replayStore", () => ({
  useReplayStore: (selector: (state: { isPaused: boolean; tourStepIndex: number; replayVariant: "detailed" | "fast" }) => unknown) => selector({
    isPaused: true,
    tourStepIndex: 0,
    replayVariant: "detailed",
  }),
}));

vi.mock("@/hooks/useScenario", () => ({
  useScenario: () => ({
    scenario: {
      replay_tour: [
        {
          title: "Fast scenario-owned step",
          body: "Fast replay should use the compact scenario config.",
          cta: "Continue",
        },
      ],
      replay_tour_detailed: [
        {
          title: "Detailed scenario-owned step",
          body: "Detailed replay should use the detailed scenario config.",
          cta: "Continue",
        },
      ],
    },
    loading: false,
    error: null,
  }),
}));

describe("ReplayTourOverlay", () => {
  it("prefers replay tour steps from scenario metadata", async () => {
    const { ReplayTourOverlay } = await import("@/components/replay/ReplayTourOverlay");

    render(<ReplayTourOverlay />);

    expect(screen.getByText("Detailed scenario-owned step")).toBeTruthy();
    expect(screen.getByText(/Detailed replay should use the detailed scenario config\./i)).toBeTruthy();
    expect(screen.getByText("Step 1 of 1")).toBeTruthy();
    expect(screen.queryByText("Scenario Overview")).toBeNull();
  });
});