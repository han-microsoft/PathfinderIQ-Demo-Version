/**
 * ContextInspector — overlay showing the context sent to an agent for a message.
 *
 * Displays: session ID, agent ID, agent name, thread position,
 * system prompt (fetched lazily), and instruction files.
 * Auto-populated from stores and the agent-prompt API.
 *
 * Key collaborators:
 *   - useSessionStore  — activeSessionId
 *   - useAgentStore    — agents list for display name lookup
 *   - GET /api/scenario/agent-prompt?agent_id=X — system prompt text
 *
 * Dependents:
 *   Rendered by MessageBubble on icon click.
 */

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import { useAgentStore } from "@/stores/agentStore";

interface ContextInspectorProps {
  /** The agent_name from the message (agent ID). */
  agentId: string;
  /** Position of this message within the agent's thread (1-based). */
  threadPosition: number;
  /** The message object (may contain context_snapshot). */
  message?: import("@/api/types").Message;
  /** Close the overlay. */
  onClose: () => void;
}

interface PromptData {
  agent_id: string;
  agent_name: string;
  instruction_files: string[];
  prompt_text: string;
  char_count: number;
  error?: string;
}

export function ContextInspector({ agentId, threadPosition, message, onClose }: ContextInspectorProps) {
  const sessionId = useSessionStore((s) => s.activeSessionId) ?? "(none)";
  const session = useSessionStore((s) => s.activeSession);
  const agents = useAgentStore((s) => s.agents);
  const agentInfo = agents.find((a) => a.id === agentId);
  const agentDisplayName = agentInfo?.name ?? agentId;
  const toolCount = agentInfo?.tool_count ?? 0;
  const isDefault = agentInfo?.is_default ?? false;

  // Thread info from session
  const thread = session?.threads?.[agentId];
  const agentSessionId = thread?.agent_session_id ?? "(no thread)";

  // Context snapshot from the message (v3)
  const snap = message?.context_snapshot;

  const [promptData, setPromptData] = useState<PromptData | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);

  /* Fetch prompt text lazily on first expand */
  useEffect(() => {
    if (!showPrompt || promptData) return;
    setLoading(true);
    import('@/api/scenarioApi')
      .then(({ getAgentPrompt }) => getAgentPrompt(agentId))
      .then((d) => setPromptData(d as unknown as PromptData))
      .catch(() => setPromptData({ agent_id: agentId, agent_name: agentId, instruction_files: [], prompt_text: "(failed to load)", char_count: 0, error: "fetch failed" }))
      .finally(() => setLoading(false));
  }, [showPrompt, promptData, agentId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-neutral-bg2 border border-border rounded-xl shadow-2xl w-[600px] max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-text-primary">Context Inspector</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 text-xs">
          {/* Identity */}
          <Section title="Identity">
            <Row label="Session ID" value={sessionId} mono />
            <Row label="Agent Session ID" value={agentSessionId} mono />
            <Row label="Agent ID" value={agentId} mono />
            <Row label="Agent Name" value={agentDisplayName} />
            <Row label="Default Agent" value={isDefault ? "Yes" : "No"} />
          </Section>

          {/* Thread */}
          <Section title="Thread">
            <Row label="Thread Position" value={`Message #${threadPosition}`} />
            <Row label="Thread Key" value={`${sessionId}:${agentId}`} mono />
          </Section>

          {/* Context Snapshot (from message data) */}
          {snap && (
            <Section title="Context Window">
              <Row label="Messages Total" value={String(snap.messages_total)} />
              <Row label="Messages Kept" value={String(snap.messages_kept)} />
              <Row label="Messages Dropped" value={String(snap.messages_dropped)} />
              <Row label="Tokens Used" value={`${(snap as Record<string, any>).tokens_used?.toLocaleString?.()} / ${(snap as Record<string, any>).tokens_budget?.toLocaleString?.()}`} />
              <Row label="Max Turns" value={(snap as Record<string, any>).max_turns === null ? "Unlimited" : String((snap as Record<string, any>).max_turns)} />
              <Row label="System Prompt" value={`${(snap as Record<string, any>).system_prompt_chars?.toLocaleString?.()} chars`} />
            </Section>
          )}

          {/* Tools */}
          <Section title="Tools">
            <Row label="Tool Count" value={String(toolCount)} />
          </Section>

          {/* System Prompt (collapsible) */}
          <div>
            <button
              onClick={() => setShowPrompt(!showPrompt)}
              className="text-xs font-semibold text-brand hover:text-brand-hover"
            >
              {showPrompt ? "▼ Hide System Prompt" : "▶ Show System Prompt"}
            </button>
            {showPrompt && (
              <div className="mt-2 space-y-2">
                {loading && <p className="text-text-muted animate-pulse">Loading…</p>}
                {promptData && !promptData.error && (
                  <>
                    <Row label="Char Count" value={String(promptData.char_count)} />
                    <div>
                      <p className="text-text-muted mb-1">Instruction Files:</p>
                      <ul className="list-disc list-inside text-text-secondary">
                        {promptData.instruction_files.map((f, i) => (
                          <li key={i} className="font-mono text-[10px]">{f}</li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <p className="text-text-muted mb-1">Full Prompt:</p>
                      <pre className="bg-neutral-bg1 border border-border rounded p-2 text-[10px] text-text-secondary overflow-auto max-h-[300px] whitespace-pre-wrap">
                        {promptData.prompt_text}
                      </pre>
                    </div>
                  </>
                )}
                {promptData?.error && (
                  <p className="text-status-error">{promptData.error}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Helper components ───────────────────────────────────────────────────── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">{title}</h4>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-text-muted">{label}</span>
      <span className={`text-text-secondary ${mono ? "font-mono text-[10px]" : ""}`}>{value}</span>
    </div>
  );
}
