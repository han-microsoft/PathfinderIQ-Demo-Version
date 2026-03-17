import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const noop = vi.fn();

vi.mock("@/stores/chatStore", () => ({
  useChatStore: { getState: () => ({ sendMessage: vi.fn() }) },
}));

vi.mock("@/stores/sessionStore", () => ({
  useSessionStore: { getState: () => ({ activeSessionId: null }) },
}));

vi.mock("@/stores/agentStore", () => ({
  useAgentStore: { getState: () => ({ activeAgentId: "orchestrator", fetchAgents: vi.fn() }) },
}));

vi.mock("@/stores/observabilityStore", () => ({
  useObservabilityStore: (selector: (state: unknown) => unknown) => selector({ isVisible: false, toggle: noop }),
}));

vi.mock("@/stores/chatSettingsStore", () => ({
  MIN_CHAT_TEXT: 80,
  MAX_CHAT_TEXT: 140,
  useChatSettingsStore: (selector: (state: unknown) => unknown) => selector({
    uiScale: 1,
    setUiScale: noop,
    graphVisible: false,
    chatTextScale: 100,
    setChatTextScale: noop,
    toggleGraph: noop,
  }),
}));

vi.mock("@/hooks/useScenario", () => ({
  useScenario: () => ({
    scenario: {
      scenario_name: "telecom-playground-v2",
      display_name: "Telecom Playground",
      description: "Scenario description",
      domain: "telecom",
      version: "test",
      use_cases: [],
      example_questions: [],
    },
  }),
}));

vi.mock("@/stores/scenarioStore", () => ({
  useScenarioStore: () => ({
    items: [{ name: "telecom-playground-v2", display_name: "Telecom Playground", is_active: true }],
    switchItem: vi.fn(),
    switching: false,
    error: null,
  }),
}));

vi.mock("@/auth", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    user: null,
    logout: noop,
    switchAccount: noop,
  }),
}));

vi.mock("@/api/client", () => ({
  submitFeedback: vi.fn(),
}));

vi.mock("@/stores/replayStore", () => ({
  useReplayStore: {
    getState: () => ({ startReplay: vi.fn() }),
    setState: vi.fn(),
  },
}));

vi.mock("@/features/replay/replayEngine", () => ({
  runReplay: vi.fn(),
}));

vi.mock("@/ThemeContext", () => ({
  THEMES: [{ id: "default", label: "Default", icon: "D" }],
  useTheme: () => ({
    theme: "default",
    currentMeta: { logo: "/logo.png" },
    setTheme: noop,
  }),
}));

vi.mock("@/components/layout/ScenarioOverlay", () => ({
  ScenarioOverlay: () => <div>ScenarioOverlay</div>,
}));

vi.mock("@/components/layout/DeveloperNotesOverlay", () => ({
  DeveloperNotesOverlay: () => <div>DeveloperNotesOverlay</div>,
}));

vi.mock("@/components/sidebar/SessionMetrics", () => ({
  SessionMetrics: () => <div>SessionMetrics</div>,
}));

vi.mock("@/components/sidebar/ServiceHealth", () => ({
  ServiceHealth: () => <div>ServiceHealth</div>,
}));

vi.mock("@/components/sidebar/ConversationList", () => ({
  ConversationList: () => <div>ConversationList</div>,
}));

describe("Header settings modal", () => {
  it("does not render model or backend selectors", async () => {
    const { Header } = await import("@/components/layout/Header");

    render(<Header />);
    fireEvent.click(screen.getByTitle("Expand Settings"));
    fireEvent.click(screen.getByTitle("Open settings"));

    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
    expect(screen.queryByText("Model")).toBeNull();
    expect(screen.queryByText("Graph Backend")).toBeNull();
    expect(screen.getByText(/Runtime model and graph backend selection are owned by the active scenario\./i)).toBeTruthy();
  });
});