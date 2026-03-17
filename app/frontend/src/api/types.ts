/**
 * TypeScript types mirroring the backend Pydantic models.
 *
 * Module role:
 *   The frontend's single source of truth for API shapes. Every interface here
 *   corresponds 1:1 to a Pydantic model in backend/app/models.py. Changes to
 *   the backend models MUST be reflected here to maintain type safety.
 *
 * Type groups:
 *   Enums        — Role, MessageStatus, StreamEventType, ToolCallStatus
 *   Content      — ContentPart (text | thinking | tool_call)
 *   Core Models  — ToolCall, Message, Session, SessionSummary
 *   API I/O      — ChatRequest, CreateSessionRequest, UpdateSessionRequest
 *   SSE Events   — StreamMetadata
 *
 * Key collaborators:
 *   - backend/app/models.py      — Python source of truth (keep in sync)
 *   - API_CONTRACT.md            — human-readable specification
 *   - api/client.ts              — uses these types for API call signatures
 *   - stores/chatStore.ts        — uses Message, StreamMetadata, ContentPart
 *   - stores/sessionStore.ts     — uses Session, SessionSummary
 */

// ── Enums ───────────────────────────────────────────────────────────────────

export type Role = "system" | "user" | "assistant" | "tool";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "complete"
  | "error"
  | "aborted";

export type StreamEventType =
  | "token"
  | "tool_call_start"
  | "tool_call_delta"
  | "tool_call_end"
  | "tool_result"
  | "thinking"
  | "citation"
  | "error"
  | "done"
  | "aborted"
  | "metadata"
  | "rate_limited"
  | "keepalive";

// ── Tool Calls ──────────────────────────────────────────────────────────────

export type ToolCallStatus = "pending" | "running" | "complete" | "error";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: string | null;
  status: ToolCallStatus;
  summary?: string;
  duration_ms?: number | null;
  /** Epoch ms when this tool call started — used for live timer persistence across tab switches. */
  start_ms?: number | null;
}

// ── Content Parts (ordered, interleaved rendering) ──────────────────────────

export type ContentPart =
  | { type: "text"; text: string }
  | { type: "thinking"; text: string }
  | { type: "tool_call"; toolCall: ToolCall }

// ── Messages ────────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  role: Role;
  content: string;
  parts: ContentPart[];      // ordered content parts for interleaved rendering
  status: MessageStatus;
  tool_calls: ToolCall[];
  agent_name: string;          // Which agent authored this message
  context_snapshot?: Record<string, unknown> | null;  // Audit record of LLM context
  created_at: string; // ISO 8601
}

// ── Agent Threads ───────────────────────────────────────────────────────────

/** Per-agent conversation thread within a session (schema v3). */
export interface AgentThread {
  agent_session_id: string;
  agent_id: string;
  agent_name: string;
  messages: Message[];
  created_at: string;
}

// ── Agent Info ──────────────────────────────────────────────────────────────

/** Agent metadata returned by GET /api/agents. */
export interface AgentInfo {
  id: string;
  name: string;
  description: string;
  tools: string[];
  is_default: boolean;
  tool_count: number;
  headshot_url?: string | null;
  full_body_url?: string | null;
  product_summary?: string | null;
  powered_by?: {
    logo_url: string;
    label: string;
    description: string;
  }[];
}

// ── Sessions ────────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  title: string;
  schema_version: number;
  scenario_name: string;
  user_id: string;
  threads: Record<string, AgentThread>;  // keyed by agent_id (schema v3)
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: string;
  title: string;
  scenario_name: string;
  user_id: string;
  message_count: number;
  tool_call_count: number;
  thinking_count: number;
  user_prompt_count: number;
  agent_response_count: number;
  created_at: string;
  updated_at: string;
}

// ── API Requests ────────────────────────────────────────────────────────────

export interface ChatRequest {
  content: string;
  max_context_turns?: number | null;
}

export interface CreateSessionRequest {
  title?: string;
}

export interface UpdateSessionRequest {
  title: string;
}

// ── SSE Events ──────────────────────────────────────────────────────────────

export interface StreamMetadata {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms: number;
  model: string;
  assistant_message_id: string;
  estimated_cost_usd?: number | null;
}

// ── Scenarios ───────────────────────────────────────────────────────────────

/** Scenario info returned by GET /api/scenarios. */
export interface ScenarioInfo {
  name: string;
  display_name: string;
  description: string;
  has_topology: boolean;
  is_active: boolean;
}

export interface ReplayTourStep {
  title: string;
  body: string;
  cta: string;
  agentImage?: string;
  poweredBy?: {
    logoSrc: string;
    label: string;
    description: string;
  };
}

export interface ReplayHighlight {
  title: string;
  body: string;
}

export interface ScenarioDetail {
  scenario_name: string;
  display_name: string;
  description: string;
  domain: string;
  version: string;
  use_cases: string[];
  example_questions: string[];
  graph_schema?: {
    vertices: { label: string; properties: string[] }[];
    edges: { label: string; source: string; target: string }[];
  };
  demo_flows?: {
    title: string;
    steps: { prompt: string }[];
  }[];
  replay_tour?: ReplayTourStep[];
  replay_tour_detailed?: ReplayTourStep[];
  replay_highlights?: Record<string, ReplayHighlight>;
  replay_conversation_url?: string | null;
}

// ── Auth (continued) ────────────────────────────────────────────────────────

/** Response from GET /api/auth_setup — MSAL configuration for the frontend. */
export interface AuthSetupResponse {
  useLogin: boolean;
  clientId?: string;
  authority?: string;
  scopes?: string[];
}
