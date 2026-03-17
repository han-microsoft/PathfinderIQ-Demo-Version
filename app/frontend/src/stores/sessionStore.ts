/**
 * Session store — manages session list and active session.
 *
 * Module role:
 *   Zustand store with async actions that call the API client for session
 *   CRUD operations. Owns the session sidebar state: which sessions exist,
 *   which one is active, and what its full message history looks like.
 *
 * State:
 *   sessions         — Array of SessionSummary (no messages, for sidebar list)
 *   activeSessionId  — ID of the currently selected session
 *   activeSession    — Full Session object with messages (loaded on selection)
 *   loading/error    — UI loading and error states
 *
 * Lifecycle:
 *   1. Component mounts → fetchSessions() loads sidebar list
 *   2. User creates session → createSession() → auto-selects it
 *   3. User clicks session → selectSession() → loads full messages
 *   4. Chat completes → chatStore calls refreshActiveSession() to sync
 *
 * Key collaborators:
 *   - api/client.ts         — all session CRUD HTTP requests
 *   - stores/chatStore.ts   — calls refreshActiveSession after streaming
 *   - components/session/SessionSidebar — renders session list
 *
 * Dependents:
 *   Used by: SessionSidebar, ChatPanel, ChatInput, Header
 */

import { create } from "zustand";
import type { Session, SessionSummary } from "@/api/types";
import * as api from "@/api/client";

interface SessionState {
  // State
  sessions: SessionSummary[];
  activeSessionId: string | null;
  activeSession: Session | null;
  loading: boolean;
  error: string | null;

  // Actions
  fetchSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<Session>;
  selectSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  saveSession: (sessionId: string) => Promise<void>;
  resetDefaults: () => Promise<void>;
  clearError: () => void;

  // Internal — called by chatStore after messages change
  refreshActiveSession: () => Promise<void>;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  activeSession: null,
  loading: false,
  error: null,

  fetchSessions: async () => {
    set({ loading: true, error: null });
    try {
      const sessions = await api.listSessions();
      set({ sessions, loading: false });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  createSession: async (title?: string) => {
    try {
      const session = await api.createSession(title ? { title } : undefined);
      // Prepend to list and select it
      set((state) => ({
        sessions: [
          {
            id: session.id,
            title: session.title,
            scenario_name: "",
            user_id: session.user_id,
            message_count: 0,
            tool_call_count: 0,
            thinking_count: 0,
            user_prompt_count: 0,
            agent_response_count: 0,
            created_at: session.created_at,
            updated_at: session.updated_at,
          },
          ...state.sessions,
        ],
        activeSessionId: session.id,
        activeSession: session,
      }));
      return session;
    } catch (err) {
      set({ error: (err as Error).message });
      throw err;
    }
  },

  selectSession: async (sessionId: string) => {
    set({ loading: true, error: null, activeSessionId: sessionId });
    try {
      const session = await api.getSession(sessionId);
      set({ activeSession: session, loading: false });
    } catch (err) {
      set({ error: (err as Error).message, loading: false });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await api.deleteSession(sessionId);
      const { activeSessionId } = get();
      set((state) => ({
        sessions: state.sessions.filter((s) => s.id !== sessionId),
        ...(activeSessionId === sessionId
          ? { activeSessionId: null, activeSession: null }
          : {}),
      }));
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  renameSession: async (sessionId: string, title: string) => {
    try {
      await api.updateSession(sessionId, { title });
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, title } : s,
        ),
        activeSession:
          state.activeSession?.id === sessionId
            ? { ...state.activeSession, title }
            : state.activeSession,
      }));
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  refreshActiveSession: async () => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      const session = await api.getSession(activeSessionId);
      set({ activeSession: session });
      // Also update the summary in the list
      /* Count messages across all threads for the sidebar summary */
      const totalMessages = Object.values(session.threads ?? {}).reduce(
        (sum, t) => sum + (t.messages?.length ?? 0), 0
      );
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === activeSessionId
            ? {
                ...s,
                title: session.title,
                message_count: totalMessages,
                updated_at: session.updated_at,
              }
            : s,
        ),
      }));
    } catch {
      // Silently fail — session may have been deleted
    }
  },

  saveSession: async (sessionId: string) => {
    try {
      await api.saveSession(sessionId);
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  resetDefaults: async () => {
    try {
      await api.resetDefaults();
      // Refresh the session list to show newly cloned demos
      await get().fetchSessions();
    } catch (err) {
      set({ error: (err as Error).message });
    }
  },

  clearError: () => set({ error: null }),
}));
