/**
 * Chat store — per-agent message slices and streaming state.
 *
 * Module role:
 *   Zustand store that owns all chat-related state, organized as a map of
 *   per-agent slices. Each slice holds its own messages, streaming status,
 *   content parts, tool call index, and abort controller. This enables
 *   independent, concurrent chat sessions per agent tab.
 *
 * State machine (per slice):
 *   IDLE → user sends message → STREAMING → events arrive → DONE/ERROR
 *                                    ↓
 *                                  ABORT → ABORTED
 *
 * Key collaborators:
 *   - api/client.ts:streamChat     — SSE streaming with typed callbacks
 *   - stores/sessionStore.ts       — refreshes session after stream completes
 *   - stores/agentStore.ts         — provides activeAgentId
 *   - components/chat/MessageList  — renders slice messages
 *   - components/chat/StreamingIndicator — renders streamingParts during streaming
 *
 * Dependents:
 *   Used by: ChatPanel, ChatInput, MessageList, StreamingIndicator, MessageBubble
 */

import { create } from "zustand";
import type {
  Message,
  StreamMetadata,
  ContentPart,
  AgentThread,
} from "@/api/types";
import * as api from "@/api/client";
import { useSessionStore } from "./sessionStore";
import { legacyToParts } from "@/features/chat/partUtils";
import { buildAssistantMessage } from "@/features/chat/messageBuilder";
import { syncMessageIds } from "@/features/chat/idSync";
import {
  appendToken as _appendToken,
  startToolCall as _startToolCall,
  endToolCall as _endToolCall,
  applyToolResult as _applyToolResult,
} from "@/features/chat/sliceReducers";

type ChatStatus = "idle" | "streaming" | "error";



// ── Per-agent chat slice ────────────────────────────────────────────────────

/** All state for one agent's chat tab. */
export interface AgentChatSlice {
  messages: Message[];
  status: ChatStatus;
  streamingParts: ContentPart[];
  streamingToolIndex: Map<string, number>;
  /** Tracks tool call start timestamps for duration calculation (tool_id → Date.now()) */
  _toolStartTimes: Map<string, number>;
  hasSeenToolCall: boolean;
  lastEventWasToolResult: boolean;
  lastMetadata: StreamMetadata | null;
  error: string | null;
  errorCode: string | null;
  errorId: string | null;
  rateLimitCountdown: number | null;
  _sendTimestamp: number | null;
  _firstTokenReceived: boolean;
  ttftMs: number | null;
  ttltMs: number | null;
  ttftHistory: number[];
  ttltHistory: number[];
  _abortController: AbortController | null;
  _streamingTimeout: ReturnType<typeof setTimeout> | null;
}

/** Factory: creates a default empty slice. */
function createDefaultSlice(): AgentChatSlice {
  return {
    messages: [],
    status: "idle",
    streamingParts: [],
    streamingToolIndex: new Map(),
    _toolStartTimes: new Map(),
    hasSeenToolCall: false,
    lastEventWasToolResult: false,
    lastMetadata: null,
    error: null,
    errorCode: null,
    errorId: null,
    rateLimitCountdown: null,
    _sendTimestamp: null,
    _firstTokenReceived: false,
    ttftMs: null,
    ttltMs: null,
    ttftHistory: [],
    ttltHistory: [],
    _abortController: null,
    _streamingTimeout: null,
  };
}

// ── Store ────────────────────────────────────────────────────────────────────

interface ChatState {
  /** Per-agent chat state. Keyed by agent ID (e.g. "orchestrator"). */
  slices: Record<string, AgentChatSlice>;

  /** Get the slice for an agent (lazy-creates if missing). */
  getSlice: (agentId: string) => AgentChatSlice;

  /** Send a message to a specific agent. */
  sendMessage: (sessionId: string, content: string, agentId: string) => Promise<void>;

  /** Abort an in-flight stream for a specific agent. */
  abort: (sessionId: string, agentId: string) => void;

  /** Set messages for a specific agent (e.g. on session load). */
  setMessages: (agentId: string, messages: Message[]) => void;

  /** Load a session's threads, populating each agent slice from its thread. */
  loadSessionMessages: (threads: Record<string, AgentThread>, defaultAgentId: string) => void;

  /** Clear a specific agent's chat state. */
  clearChat: (agentId: string) => void;

  /** Clear ALL agent slices (e.g. on session change). */
  clearAll: () => void;

  /** Handle a delegation event from the session event bus.
   *  Routes delegation streaming events to the correct agent slice. */
  handleDelegationEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => void;
}

// ── Slice helpers (module-level, initialized when store is created) ──────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _set: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _get: any;

function _getSlice(agentId: string): AgentChatSlice {
  const s = _get().slices[agentId];
  if (s) return s;
  const fresh = createDefaultSlice();
  _set((state: ChatState) => ({
    slices: { ...state.slices, [agentId]: fresh },
  }));
  return fresh;
}

function _setSlice(agentId: string, patch: Partial<AgentChatSlice>) {
  _set((state: ChatState) => {
    const current = state.slices[agentId] ?? createDefaultSlice();
    return {
      slices: {
        ...state.slices,
        [agentId]: { ...current, ...patch },
      },
    };
  });
}

function _updateSlice(
  agentId: string,
  updater: (slice: AgentChatSlice) => Partial<AgentChatSlice>,
) {
  _set((state: ChatState) => {
    const current = state.slices[agentId] ?? createDefaultSlice();
    const patch = updater(current);
    return {
      slices: {
        ...state.slices,
        [agentId]: { ...current, ...patch },
      },
    };
  });
}

export const useChatStore = create<ChatState>((set, get) => {
  /* Capture set/get for module-level helpers */
  _set = set;
  _get = get;

  /* Return the store object */
  const store: ChatState = {
    slices: {},

    getSlice: _getSlice,

    sendMessage: async (sessionId: string, content: string, agentId: string) => {
      const slice = _getSlice(agentId);
      if (slice.status === "streaming") return;

      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        role: "user",
        content,
        parts: [{ type: "text", text: content }],
        status: "complete",
        tool_calls: [],
        agent_name: "",
        created_at: new Date().toISOString(),
      };

      const abortController = new AbortController();

      _setSlice(agentId, {
        messages: [...slice.messages, userMessage],
        status: "streaming",
        streamingParts: [],
        streamingToolIndex: new Map(),
        hasSeenToolCall: false,
        lastEventWasToolResult: false,
        error: null,
        rateLimitCountdown: null,
        _abortController: abortController,
        _streamingTimeout: null,
        _sendTimestamp: Date.now(),
        _firstTokenReceived: false,
        ttftMs: null,
        ttltMs: null,
      });

      // ── Idle-timeout guard (per-agent) ────────────────────────────
      const IDLE_TIMEOUT_MS = 300_000;

      const _fireStreamTimeout = () => {
        const cur = _getSlice(agentId);
        if (cur.status !== "streaming") return;
        if (cur.streamingParts.length > 0) {
          let partialMsg: Message;
          try {
            partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
          } catch (err) {
            console.error("[chatStore] buildAssistantMessage failed:", err);
            partialMsg = { id: crypto.randomUUID(), role: "assistant", content: "[Error building message]", parts: [], tool_calls: [], agent_id: agentId, agent_name: agentId, status: "error", created_at: new Date().toISOString() } as Message;
          }
          _setSlice(agentId, {
            status: "error",
            error: "Stream timed out — partial response preserved above.",
            messages: [...cur.messages, partialMsg],
            streamingParts: [],
            _abortController: null,
            _streamingTimeout: null,
          });
        } else {
          _setSlice(agentId, {
            status: "error",
            error: "Stream timed out — no response received.",
            _abortController: null,
            _streamingTimeout: null,
          });
        }
      };

      const _resetIdleTimeout = (ms: number = IDLE_TIMEOUT_MS) => {
        const cur = _getSlice(agentId);
        if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
        const tid = setTimeout(_fireStreamTimeout, ms);
        _setSlice(agentId, { _streamingTimeout: tid });
      };

      _resetIdleTimeout();

      try {
        // Read context depth from settings store for max_context_turns
        const { useChatSettingsStore } = await import("./chatSettingsStore");
        const contextDepth = useChatSettingsStore.getState().contextDepth;
        await api.streamChat(
          sessionId,
          { content, max_context_turns: contextDepth },
          {
            onToken: (token) => {
              _resetIdleTimeout();
              const st = _getSlice(agentId);
              if (!st._firstTokenReceived && st._sendTimestamp) {
                const ttft = Date.now() - st._sendTimestamp;
                _setSlice(agentId, {
                  _firstTokenReceived: true,
                  ttftMs: ttft,
                  ttftHistory: [...st.ttftHistory, ttft],
                });
              }
              if (_getSlice(agentId).rateLimitCountdown !== null) {
                _setSlice(agentId, { rateLimitCountdown: null });
              }
              _updateSlice(agentId, (s) => _appendToken(s.streamingParts, token));
            },

            onToolCallStart: (id, name) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _startToolCall(s, id, name));
            },

            onToolCallDelta: () => {},

            onToolCallEnd: (id, _name, args) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _endToolCall(s, id, args));
            },

            onToolResult: (id, name, result) => {
              _resetIdleTimeout();
              _updateSlice(agentId, (s) => _applyToolResult(s, id, name, result));
            },

            onThinking: (title, detail) => {
              _updateSlice(agentId, (s) => ({
                streamingParts: [
                  ...s.streamingParts,
                  { type: "thinking" as const, text: `**${title}**: ${detail}` },
                ],
              }));
            },

            onCitation: () => {},

            onMetadata: (data) => {
              _setSlice(agentId, { lastMetadata: data as unknown as StreamMetadata });
            },

            onRateLimited: (retryAfter) => {
              _setSlice(agentId, { rateLimitCountdown: retryAfter });
              _resetIdleTimeout((retryAfter + 120) * 1000);
            },

            onKeepalive: () => {
              _resetIdleTimeout();
            },

            onError: (error, errorCode, errorId) => {
              const cur = _getSlice(agentId);
              if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
              if (cur.streamingParts.length > 0) {
                let partialMsg: Message;
                try {
                  partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
                } catch (err) {
                  console.error("[chatStore] buildAssistantMessage failed:", err);
                  partialMsg = { id: crypto.randomUUID(), role: "assistant", content: "[Error building message]", parts: [], tool_calls: [], agent_id: agentId, agent_name: agentId, status: "error", created_at: new Date().toISOString() } as Message;
                }
                _setSlice(agentId, {
                  status: "error",
                  error,
                  errorCode: errorCode ?? null,
                  errorId: errorId ?? null,
                  messages: [...cur.messages, partialMsg],
                  streamingParts: [],
                  rateLimitCountdown: null,
                  _abortController: null,
                  _streamingTimeout: null,
                });
              } else {
                _setSlice(agentId, {
                  status: "error",
                  error,
                  errorCode: errorCode ?? null,
                  errorId: errorId ?? null,
                  rateLimitCountdown: null,
                  _abortController: null,
                  _streamingTimeout: null,
                });
              }
            },

            onDone: () => {
              const cur = _getSlice(agentId);
              if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
              const ttlt = cur._sendTimestamp ? Date.now() - cur._sendTimestamp : null;
              if (ttlt) _setSlice(agentId, { ttltMs: ttlt, ttltHistory: [...cur.ttltHistory, ttlt] });

              let assistantMessage: Message;
              try {
                assistantMessage = buildAssistantMessage(cur.streamingParts, agentId, "complete");
              } catch (err) {
                console.error("[chatStore] buildAssistantMessage failed:", err);
                assistantMessage = { id: crypto.randomUUID(), role: "assistant", content: "[Error building message]", parts: [], tool_calls: [], agent_id: agentId, agent_name: agentId, status: "error", created_at: new Date().toISOString() } as Message;
              }

              _setSlice(agentId, {
                status: "idle",
                messages: [...cur.messages, assistantMessage],
                streamingParts: [],
                streamingToolIndex: new Map(),
                hasSeenToolCall: false,
                lastEventWasToolResult: false,
                rateLimitCountdown: null,
                _abortController: null,
                _streamingTimeout: null,
              });

              const completedSessionId = useSessionStore.getState().activeSession?.id;
              useSessionStore
                .getState()
                .refreshActiveSession()
                .then(() => {
                  if (useSessionStore.getState().activeSession?.id !== completedSessionId) return;
                  const session = useSessionStore.getState().activeSession;
                  if (!session) return;
                  const localMessages = _getSlice(agentId).messages;
                  const thread = session.threads?.[agentId];
                  const serverMessages = thread?.messages?.filter((m: Message) => m.role !== "system") ?? [];
                  _setSlice(agentId, { messages: syncMessageIds(localMessages, serverMessages) });
                });
            },

            onAborted: () => {
              const cur = _getSlice(agentId);
              let abortedMessage: Message;
              try {
                abortedMessage = buildAssistantMessage(cur.streamingParts, agentId, "aborted");
              } catch (err) {
                console.error("[chatStore] buildAssistantMessage failed:", err);
                abortedMessage = { id: crypto.randomUUID(), role: "assistant", content: "[Aborted]", parts: [], tool_calls: [], agent_id: agentId, agent_name: agentId, status: "aborted", created_at: new Date().toISOString() } as Message;
              }

              _setSlice(agentId, {
                status: "idle",
                messages: [...cur.messages, abortedMessage],
                streamingParts: [],
                streamingToolIndex: new Map(),
                hasSeenToolCall: false,
                lastEventWasToolResult: false,
                _abortController: null,
              });

              const completedSessionId = useSessionStore.getState().activeSession?.id;
              useSessionStore
                .getState()
                .refreshActiveSession()
                .then(() => {
                  if (useSessionStore.getState().activeSession?.id !== completedSessionId) return;
                  const session = useSessionStore.getState().activeSession;
                  if (!session) return;
                  const localMessages = _getSlice(agentId).messages;
                  const thread = session.threads?.[agentId];
                  const serverMessages = thread?.messages?.filter((m: Message) => m.role !== "system") ?? [];
                  _setSlice(agentId, { messages: syncMessageIds(localMessages, serverMessages) });
                });
            },
          },
          abortController.signal,
          agentId,
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          _setSlice(agentId, {
            status: "error",
            error: (err as Error).message,
            _abortController: null,
          });
        }
      }
    },

    abort: (sessionId: string, agentId: string) => {
      const slice = _getSlice(agentId);
      if (slice._abortController) {
        slice._abortController.abort();
        _setSlice(agentId, { _abortController: null });
      }
      // Pass agentId so the backend can abort the correct generation.
      // During delegation the backend cascades to the orchestrator's
      // abort event, which the delegation tool checks on each update.
      api.abortGeneration(sessionId, agentId).catch(() => {});
    },

    setMessages: (agentId: string, messages: Message[]) => {
      _setSlice(agentId, {
        messages: messages.map((m) => ({
          ...m,
          parts: m.parts?.length ? m.parts : legacyToParts(m),
        })),
      });
    },

    loadSessionMessages: (threads: Record<string, AgentThread>, _defaultAgentId: string) => {
      /* Load messages from per-agent threads. Each thread's messages are
         loaded into the corresponding agent slice. System messages (role=system)
         are excluded from the rendered list but remain available in the data.
         Also restores lastMetadata from the last assistant message's
         context_snapshot so Session Metrics display on reload. */
      for (const [agentId, thread] of Object.entries(threads)) {
        const displayMessages = (thread.messages ?? []).filter((m: Message) => m.role !== "system");

        // Extract lastMetadata from the last assistant message's context_snapshot
        let restoredMetadata: StreamMetadata | null = null;
        for (let i = displayMessages.length - 1; i >= 0; i--) {
          const msg = displayMessages[i];
          if (msg.role === "assistant" && msg.context_snapshot) {
            const cs = msg.context_snapshot as Record<string, unknown>;
            restoredMetadata = {
              prompt_tokens: (cs.prompt_tokens as number) || (cs.tokens_used as number) || 0,
              completion_tokens: (cs.completion_tokens as number) || 0,
              total_tokens: (cs.total_tokens as number) || (cs.tokens_used as number) || 0,
              duration_ms: (cs.duration_ms as number) || 0,
              model: (cs.model as string) || "",
              assistant_message_id: msg.id,
              estimated_cost_usd: (cs.estimated_cost_usd as number) || undefined,
            };
            break;
          }
        }

        _setSlice(agentId, {
          messages: displayMessages.map((m: Message) => ({
            ...m,
            parts: m.parts?.length ? m.parts : legacyToParts(m),
          })),
          ...(restoredMetadata ? { lastMetadata: restoredMetadata } : {}),
        });
      }
    },

    clearChat: (agentId: string) => {
      const cur = _getSlice(agentId);
      if (cur._abortController) cur._abortController.abort();
      if (cur._streamingTimeout) clearTimeout(cur._streamingTimeout);
      _setSlice(agentId, createDefaultSlice());
    },

    clearAll: () => {
      const { slices } = get();
      for (const slice of Object.values(slices)) {
        if (slice._abortController) slice._abortController.abort();
        if (slice._streamingTimeout) clearTimeout(slice._streamingTimeout);
      }
      set({ slices: {} });
    },

    handleDelegationEvent: (agentId: string, eventType: string, data: Record<string, unknown>) => {
      switch (eventType) {
        case "delegation_start": {
          /* Set streaming state immediately — the user message will
             appear after the next refresh (on "done"). No need to
             fetch the full session here; it blocks the UI. */
          _setSlice(agentId, {
            status: "streaming",
            streamingParts: [],
            streamingToolIndex: new Map(),
            hasSeenToolCall: false,
            lastEventWasToolResult: false,
            error: null,
          });
          break;
        }
        case "thinking": {
          /* Start a new thinking block (subsequent "token" events append to it) */
          _updateSlice(agentId, (s) => {
            const parts = [...s.streamingParts];
            const token = (data.token as string) || "";
            parts.push({ type: "thinking", text: token });
            return { streamingParts: parts };
          });
          break;
        }
        case "token": {
          _updateSlice(agentId, (s) => _appendToken(s.streamingParts, (data.token as string) || ""));
          break;
        }
        case "tool_call_start": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          _updateSlice(agentId, (s) => _startToolCall(s, id, name));
          break;
        }
        case "tool_call_end": {
          const id = (data.id as string) || "";
          const args = (data.arguments as Record<string, unknown>) || {};
          _updateSlice(agentId, (s) => _endToolCall(s, id, args));
          break;
        }
        case "tool_result": {
          const id = (data.id as string) || "";
          const name = (data.name as string) || "";
          const result = (data.result as string) || "";
          _updateSlice(agentId, (s) => _applyToolResult(s, id, name, result));
          break;
        }
        case "done": {
          /* Build the assistant message from accumulated parts */
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const assistantMessage = buildAssistantMessage(cur.streamingParts, agentId, "complete");
            _setSlice(agentId, {
              status: "idle",
              messages: [...cur.messages, assistantMessage],
              streamingParts: [],
              streamingToolIndex: new Map(),
              hasSeenToolCall: false,
              lastEventWasToolResult: false,
            });
            /* No refreshActiveSession here — the orchestrator's onDone handler
               already calls refreshActiveSession when the full stream completes.
               Firing it mid-stream causes a large JSON fetch + React render storm
               while the orchestrator is still streaming tokens, freezing the UI. */
          } else {
            _setSlice(agentId, { status: "idle" });
          }
          break;
        }
        case "error": {
          const errorMsg = (data.error as string) || "Delegation failed";
          const cur = _getSlice(agentId);
          if (cur.streamingParts.length > 0) {
            const partialMsg = buildAssistantMessage(cur.streamingParts, agentId, "error");
            _setSlice(agentId, {
              status: "error",
              error: errorMsg,
              messages: [...cur.messages, partialMsg],
              streamingParts: [],
            });
          } else {
            _setSlice(agentId, { status: "error", error: errorMsg });
          }
          break;
        }
        default:
          console.warn("[handleDelegationEvent] Unknown event type:", eventType, data);
          break;
      }
    },
  };
  return store;
});
