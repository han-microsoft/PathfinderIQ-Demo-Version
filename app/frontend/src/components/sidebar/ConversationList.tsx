/**
 * ConversationList — session list panel with CRUD, status dots, and badges.
 *
 * Consumes sessionStore and chatStore directly via Zustand selectors.
 * Self-contained — no props needed from the parent sidebar.
 *
 * Streaming guard: while a chat is in progress (status === "streaming"),
 * session creation and switching are blocked. Non-active items are visually
 * dimmed and the New button is disabled with a tooltip explaining why.
 */

import { useCallback, useEffect, useState } from "react";
import {
  MessageSquarePlus,
  Trash2,
  PenLine,
  Check,
  X,
  Save,
  RotateCcw,
  Download,
} from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";
import * as api from "@/api/client";
import { useTranslation } from "@/hooks/useTranslation";

export function ConversationList({ onCollapse, showHeader = true }: { onCollapse?: () => void; showHeader?: boolean }) {
  const sessions = useSessionStore((s) => s.sessions);
  const activeSessionId = useSessionStore((s) => s.activeSessionId);
  const fetchSessions = useSessionStore((s) => s.fetchSessions);
  const createSession = useSessionStore((s) => s.createSession);
  const selectSession = useSessionStore((s) => s.selectSession);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const renameSession = useSessionStore((s) => s.renameSession);
  const saveSession = useSessionStore((s) => s.saveSession);
  const resetDefaults = useSessionStore((s) => s.resetDefaults);
  const loadSessionMessages = useChatStore((s) => s.loadSessionMessages);
  const clearAll = useChatStore((s) => s.clearAll);
  const activeAgentId = useAgentStore((s) => s.activeAgentId) ?? "orchestrator";
  const chatSlice = useChatStore((s) => s.getSlice(activeAgentId));

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  // Confirmation state: { sessionId, action } — shows inline confirmation banner
  const [confirmAction, setConfirmAction] = useState<{
    id: string;
    action: "save" | "delete" | "reset";
    label: string;
  } | null>(null);

  /* Whether the chat is currently streaming — used to block session switching */
  const isStreaming = chatSlice.status === "streaming";
  const { t } = useTranslation();

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const handleCreate = useCallback(async () => {
    if (isStreaming) return; // Block while streaming
    clearAll();
    const session = await createSession();
    loadSessionMessages(session.threads ?? {}, activeAgentId);
  }, [createSession, loadSessionMessages, clearAll, isStreaming, activeAgentId]);

  const handleSelect = useCallback(
    async (id: string) => {
      if (id === activeSessionId) return;
      if (isStreaming) return; // Block while streaming
      clearAll();
      // Refresh session list so the old session's counts update in the sidebar
      fetchSessions();
      await selectSession(id);
      const session = useSessionStore.getState().activeSession;
      if (session) loadSessionMessages(session.threads ?? {}, activeAgentId);
    },
    [activeSessionId, clearAll, selectSession, loadSessionMessages, fetchSessions, isStreaming, activeAgentId],
  );

  const handleSave = useCallback(async (id: string) => {
    const session = sessions.find((s) => s.id === id);
    const title = session?.title ?? "this conversation";
    setConfirmAction({ id, action: "save", label: `Save "${title}" to disk? This exports the conversation as a JSON file.` });
  }, [sessions]);

  const handleConfirmAction = useCallback(async () => {
    if (!confirmAction) return;
    const { id, action } = confirmAction;
    setConfirmAction(null);
    switch (action) {
      case "save":
        await saveSession(id);
        setSavedId(id);
        setTimeout(() => setSavedId(null), 2000);
        break;
      case "delete":
        await deleteSession(id);
        if (id === activeSessionId) clearAll();
        break;
      case "reset":
        await resetDefaults();
        break;
    }
  }, [confirmAction, saveSession, deleteSession, activeSessionId, clearAll, resetDefaults]);

  const handleDelete = useCallback((id: string) => {
    const session = sessions.find((s) => s.id === id);
    const title = session?.title ?? "this conversation";
    setConfirmAction({ id, action: "delete", label: `Delete "${title}"? This cannot be undone.` });
  }, [sessions]);

  /** Download the full conversation (with messages) as a JSON file to the user's machine. */
  const handleDownload = useCallback(async (id: string) => {
    try {
      // Use activeSession if it matches, otherwise fetch from the backend
      const { activeSession } = useSessionStore.getState();
      const session = activeSession?.id === id ? activeSession : await api.getSession(id);
      const blob = new Blob([JSON.stringify(session, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      // Sanitize title for filename — replace non-alphanumeric chars with underscores
      const safeName = (session.title || "conversation").replace(/[^a-zA-Z0-9-_ ]/g, "_").trim();
      a.download = `${safeName}.json`;
      document.body.appendChild(a);
      a.click();
      // Cleanup the temporary link and object URL
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      /* Download failed silently — session may not exist */
    }
  }, []);

  const handleStartRename = useCallback((id: string, currentTitle: string) => {
    setEditingId(id);
    setEditTitle(currentTitle);
  }, []);

  const handleConfirmRename = useCallback(async () => {
    if (editingId && editTitle.trim()) await renameSession(editingId, editTitle.trim());
    setEditingId(null);
  }, [editingId, editTitle, renameSession]);

  return (
    <>
      {/* Header — shown in standalone mode (right sidebar) */}
      {showHeader && (
        <div className="border-b border-border bg-header-bg px-4 py-2 shrink-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-header-text uppercase tracking-wider">{t("sidebar.conversations")}</h2>
            {onCollapse && (
              <button
                onClick={onCollapse}
                className="rounded-md p-1 text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
                title={t("sidebar.collapseConversations")}
                aria-label={t("sidebar.collapseConversations")}
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Action buttons — always visible */}
      <div className={`flex items-center gap-1 ${showHeader ? "px-4 py-1 border-b border-border bg-header-bg" : "mb-1"}`}>
          <button
            onClick={() => setConfirmAction({ id: "__reset__", action: "reset", label: t("sidebar.resetDemoConfirm") })}
            disabled={isStreaming}
            className={`flex items-center gap-1 rounded-lg px-2 py-1 text-xs transition-colors shrink-0 ${
              isStreaming
                ? "text-text-muted cursor-not-allowed opacity-50"
                : "text-text-muted hover:text-brand hover:bg-neutral-bg3"
            }`}
            aria-label={t("sidebar.resetDemoTitle")}
            title={t("sidebar.resetDemoTitle")}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleCreate}
            disabled={isStreaming}
            className={`flex items-center gap-1 rounded-lg px-2 py-1 text-xs transition-colors shrink-0 ${
              isStreaming
                ? "text-text-muted cursor-not-allowed opacity-50"
                : "text-brand hover:bg-neutral-bg3"
            }`}
            aria-label={t("sidebar.newConversation")}
            title={isStreaming ? t("sidebar.waitForResponse") : t("sidebar.newConversation")}
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            <span>{t("sidebar.new")}</span>
          </button>
      </div>

      {/* Confirmation banner */}
      {confirmAction && (
        <div className="mx-2 my-1 p-2 rounded-lg bg-neutral-bg3 border border-border text-xs" onClick={(e) => e.stopPropagation()}>
          <p className="text-text-primary mb-2">{confirmAction.label}</p>
          <div className="flex gap-2">
            <button
              onClick={handleConfirmAction}
              className={`px-3 py-1 rounded-md text-white text-xs font-semibold transition-colors ${
                confirmAction.action === "delete"
                  ? "bg-status-error hover:bg-status-error"
                  : "bg-brand hover:bg-brand/80"
              }`}
            >
              {t("common.confirm")}
            </button>
            <button
              onClick={() => setConfirmAction(null)}
              className="px-3 py-1 rounded-md bg-neutral-bg4 text-text-muted hover:text-text-primary text-xs transition-colors"
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-1" aria-label="Conversation list">
        {sessions.length === 0 && (
          <p className="px-4 py-6 text-center text-xs text-text-muted">{t("sidebar.noConversations")}</p>
        )}
        {sessions.map((session) => {
          const isActive = session.id === activeSessionId;
          const isEditing = editingId === session.id;

          const isSessionStreaming = isActive && chatSlice.status === "streaming";
          const isEmpty = (session.message_count ?? 0) === 0 && !isSessionStreaming;
          const statusLabel = isSessionStreaming ? t("sidebar.status.inProgress") : isEmpty ? t("sidebar.status.empty") : t("sidebar.status.completed");
          const dotColor = isSessionStreaming ? "bg-status-warning" : isEmpty ? "bg-text-muted/40" : "bg-status-success";
          const statusTextColor = isSessionStreaming ? "text-status-warning" : isEmpty ? "text-text-muted" : "text-status-success";

          return (
            <div
              key={session.id}
              className={`group relative flex items-center gap-2 px-3 py-1.5 mx-2 rounded-lg transition-colors ${
                isActive
                  ? "bg-neutral-bg3 text-text-primary"
                  : isStreaming
                    ? "text-text-muted/50 cursor-not-allowed"
                    : "text-text-secondary hover:bg-neutral-bg3/50 cursor-pointer"
              }`}
              onClick={() => handleSelect(session.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && handleSelect(session.id)}
              aria-current={isActive ? "true" : undefined}
            >
              <div className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-1">
                  {isEditing ? (
                    <div className="flex items-center gap-1">
                      <input
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleConfirmRename();
                          if (e.key === "Escape") setEditingId(null);
                          e.stopPropagation();
                        }}
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 rounded bg-neutral-bg1 px-1.5 py-0.5 text-sm outline-none border border-brand"
                        autoFocus
                      />
                      <button onClick={(e) => { e.stopPropagation(); handleConfirmRename(); }} className="text-status-success hover:text-status-success">
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(null); }} className="text-text-muted hover:text-text-primary">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <p className="truncate text-sm flex-1">{session.title}</p>
                  )}
                  <span className={`text-xs font-medium shrink-0 ${statusTextColor}`}>{statusLabel}</span>
                </div>
                {session.scenario_name && (
                  <span className="inline-block mt-0.5 text-[10px] px-1.5 py-0 rounded-full bg-brand/15 text-brand truncate max-w-[120px]">
                    {session.scenario_name}
                  </span>
                )}
              </div>

              {!isEditing && (
                <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-neutral-bg3 rounded-md px-0.5">
                  <button onClick={(e) => { e.stopPropagation(); handleDownload(session.id); }}
                    className="rounded p-1 text-text-muted hover:text-brand hover:bg-brand/10 transition-colors"
                    title={t("sidebar.downloadTitle")}>
                    <Download className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); handleSave(session.id); }}
                    className={`rounded p-1 transition-colors ${savedId === session.id ? "text-status-success" : "text-text-muted hover:text-brand hover:bg-brand/10"}`}
                    title={t("sidebar.saveTitle")}>
                    {savedId === session.id ? <Check className="h-3.5 w-3.5" /> : <Save className="h-3.5 w-3.5" />}
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); handleStartRename(session.id, session.title); }}
                    className="rounded p-1 text-text-muted hover:text-text-primary hover:bg-neutral-bg4"
                    title={t("sidebar.renameTitle")}>
                    <PenLine className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={(e) => { e.stopPropagation(); handleDelete(session.id); }}
                    className="rounded p-1 transition-colors text-text-muted hover:text-status-error hover:bg-status-error/10"
                    title={t("sidebar.deleteTitle")}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </>
  );
}
