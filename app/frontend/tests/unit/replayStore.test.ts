import { describe, expect, it } from "vitest";

import { useReplayStore } from "@/stores/replayStore";

describe("replayStore", () => {
  it("configures detailed replay defaults when starting the detailed variant", () => {
    useReplayStore.getState().startReplay("detailed");

    const state = useReplayStore.getState();

    expect(state.replayVariant).toBe("detailed");
    expect(state.speedMultiplier).toBe(1);
    expect(state.skipAnnotations).toBe(false);
  });

  it("configures fast replay defaults when starting the fast variant", () => {
    useReplayStore.getState().startReplay("fast");

    const state = useReplayStore.getState();

    expect(state.replayVariant).toBe("fast");
    expect(state.speedMultiplier).toBe(4);
    expect(state.skipAnnotations).toBe(true);
  });
});