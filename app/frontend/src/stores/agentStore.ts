/**
 * Agent store — agent definitions + active tab selection.
 *
 * Module role:
 *   Fetches agent metadata from GET /api/agents and tracks which agent tab
 *   is currently active. The tab bar reads agents from this store; the chat
 *   store uses activeAgentId to determine which slice to render.
 *
 * Key collaborators:
 *   - api/client.ts:getAgents()       — fetches agent list
 *   - components/chat/AgentTabBar.tsx  — renders tabs from agents array
 *   - stores/chatStore.ts             — reads activeAgentId for slice routing
 *
 * Dependents:
 *   Used by: AgentTabBar, ChatPanel, ChatInput, App.tsx (init)
 */

import { create } from "zustand";
import type { AgentInfo } from "@/api/types";
import * as api from "@/api/client";

interface AgentStore {
  /** All agents defined in the active scenario. */
  agents: AgentInfo[];
  /** Currently selected agent tab. Null until agents are fetched. */
  activeAgentId: string | null;
  /** If set, the agent to return to when "Return to Origin" is clicked.
   *  Set by "View Tab" on delegation tool calls. */
  returnToAgentId: string | null;
  /** Fetch agent definitions from GET /api/agents. Sets activeAgentId to default. */
  fetchAgents: () => Promise<void>;
  /** Switch the active tab. */
  setActiveAgent: (id: string) => void;
  /** Navigate to a delegated agent's tab with return tracking. */
  viewDelegatedTab: (targetAgentId: string) => void;
  /** Return to the origin agent tab (clears returnToAgentId). */
  returnToOrigin: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  activeAgentId: null,
  returnToAgentId: null,

  fetchAgents: async () => {
    /* Retry up to 3 times with 1s backoff — handles transient failures
       during startup or hot-reload when the backend is briefly unavailable.
       Without retry, a single failed fetch leaves agents=[] permanently
       and the tab bar disappears until manual page refresh. */
    const maxRetries = 3;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const agents = await api.getAgents();
        if (agents.length === 0) {
          console.warn(`[agentStore] fetchAgents returned 0 agents (attempt ${attempt + 1})`);
          if (attempt < maxRetries) {
            await new Promise((r) => setTimeout(r, 1000));
            continue;
          }
        }
        /* Set activeAgentId to the default agent (is_default=true),
           falling back to the first agent in the list. */
        const defaultAgent = agents.find((a) => a.is_default) ?? agents[0];
        set({
          agents,
          activeAgentId: defaultAgent?.id ?? null,
        });
        return; // Success — exit retry loop
      } catch (err) {
        console.warn(`[agentStore] fetchAgents failed (attempt ${attempt + 1}/${maxRetries + 1}):`, err);
        if (attempt < maxRetries) {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    }
  },

  setActiveAgent: (id: string) => set({ activeAgentId: id, returnToAgentId: null }),

  viewDelegatedTab: (targetAgentId: string) => {
    const current = get().activeAgentId;
    set({ activeAgentId: targetAgentId, returnToAgentId: current });
  },

  returnToOrigin: () => {
    const returnTo = get().returnToAgentId;
    if (returnTo) {
      set({ activeAgentId: returnTo, returnToAgentId: null });
    }
  },
}));
