/**
 * @module Header
 *
 * Application header bar — top-level chrome displaying the app brand
 * and active scenario identity.
 *
 * Renders a fixed-height (h-12) dark bar containing:
 *   - A brand diamond icon (◆) with the text “Graph Demo — {display_name}”
 *   - A scenario name badge (rounded pill with brand accent)
 *   - A light/dark theme toggle button via {@link useTheme}
 *
 * The `display_name` and `scenario_name` are fetched from the backend
 * `/api/scenario` endpoint via {@link useScenario}. While loading,
 * “Loading…” is shown as placeholder text.
 *
 * @remarks
 * - No props — all state comes from context/hooks.
 *
 * @collaborators
 *   - {@link useScenario} — provides scenario metadata (display_name, scenario_name)
 *   - {@link useTheme}    — provides theme state and toggleTheme action
 *
 * @dependents
 *   Rendered by the root App layout at the top of the viewport.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { Search, Bug, ChevronDown, ChevronUp, Settings, Play } from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useAgentStore } from '@/stores/agentStore';
import { useTheme, THEMES } from '../../ThemeContext';
import { useScenario } from '@/hooks/useScenario';
import { useObservabilityStore } from '@/stores/observabilityStore';
import { useChatSettingsStore, MIN_CHAT_TEXT, MAX_CHAT_TEXT } from '@/stores/chatSettingsStore';
import { ScenarioOverlay } from './ScenarioOverlay';
import { ScenarioSwitcher } from './ScenarioSwitcher';
import { DeveloperNotesOverlay } from './DeveloperNotesOverlay';
import { SelectorDropdown } from './SelectorDropdown';
import { useAuth } from '../../auth';
import { submitFeedback } from '@/api/client';
import { useReplayStore } from '@/stores/replayStore';
import { runReplay } from '@/features/replay/replayEngine';
import { SessionMetrics } from '../sidebar/SessionMetrics';
import { ServiceHealth } from '../sidebar/ServiceHealth';
import { ConversationList } from '../sidebar/ConversationList';
import { useTranslation } from '@/hooks/useTranslation';
import { useLocaleStore, SUPPORTED_LOCALES } from '@/stores/localeStore';

/** Shared Tailwind classes for the sidebar navigation buttons — full-width. */
const BTN = "text-sm w-full px-3 py-2 rounded-md border font-medium transition-colors leading-tight text-left";
const BTN_DEFAULT = `${BTN} border-border bg-neutral-bg3/70 hover:bg-neutral-bg4 text-text-primary`;
const BTN_ACTIVE = `${BTN} border-brand/50 bg-brand/15 text-brand`;

/** Props for external width control (resizable sidebar). */
interface HeaderProps {
  style?: React.CSSProperties;
}

export function Header({ style }: HeaderProps) {
  const { theme, currentMeta } = useTheme();
  const { scenario } = useScenario();
  const { isAuthenticated, user, logout, switchAccount } = useAuth();
  const { t } = useTranslation();
  const obsVisible = useObservabilityStore((s) => s.isVisible);
  const toggleObs = useObservabilityStore((s) => s.toggle);
  const [showScenario, setShowScenario] = useState(false);
  const uiScale = useChatSettingsStore((s) => s.uiScale);
  const setUiScale = useChatSettingsStore((s) => s.setUiScale);
  const graphVisible = useChatSettingsStore((s) => s.graphVisible);
  const chatTextScale = useChatSettingsStore((s) => s.chatTextScale);
  const setChatTextScale = useChatSettingsStore((s) => s.setChatTextScale);
  const toggleGraph = useChatSettingsStore((s) => s.toggleGraph);
  const [showBugReport, setShowBugReport] = useState(false);
  const [showDevNotes, setShowDevNotes] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showDevMetrics, setShowDevMetrics] = useState(false);
  const [showDebugQs, setShowDebugQs] = useState(false);
  const debugQsRef = useRef<HTMLDivElement>(null);
  const [bugTitle, setBugTitle] = useState("");
  const [bugDesc, setBugDesc] = useState("");
  const [bugSubmitting, setBugSubmitting] = useState(false);
  const [bugStatus, setBugStatus] = useState<string | null>(null);

  /** Close debug Qs dropdown on outside click. */
  useEffect(() => {
    if (!showDebugQs) return;
    const handler = (e: MouseEvent) => {
      if (debugQsRef.current && !debugQsRef.current.contains(e.target as Node)) {
        setShowDebugQs(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showDebugQs]);

  const DEBUG_QUESTIONS: { label: string; prompt: string }[] = [
    { label: "\ud83e\udea3 Identity check", prompt: "Hello tell me your name and role" },
    { label: "\ud83d\udccb Show instructions", prompt: "Show me your instructions" },
    { label: "\ud83d\udcac History check", prompt: "Do we have any previous conversation history?" },
    { label: "Graph data table", prompt: "Show me a graph data table" },
    { label: "Alert table", prompt: "Show me an alert table" },
    { label: "Document search results", prompt: "Show me some document search results" },
    { label: "Greeting", prompt: "Say hello my friend!" },
    { label: "\ud83d\udcde Call Blitzorg", prompt: "Call Blitzorg the Undulant at \u234c\u235f\u2358\u27d2-\u2316\u22cf\u235c\u29eb" },
  ];

  /** Fire a debug question into the active session. */
  const handleDebugSelect = useCallback(async (prompt: string) => {
    const sessionId = useSessionStore.getState().activeSessionId;
    const agentId = useAgentStore.getState().activeAgentId ?? 'orchestrator';
    if (!sessionId) return;
    setShowDebugQs(false);
    await useChatStore.getState().sendMessage(sessionId, prompt, agentId);
  }, []);

  /** Submit the bug report form. */
  const handleBugSubmit = useCallback(async () => {
    if (!bugTitle.trim() || !bugDesc.trim()) return;
    setBugSubmitting(true);
    setBugStatus(null);
    try {
      await submitFeedback(bugTitle.trim(), bugDesc.trim());
      setBugStatus("Submitted! Thank you.");
      setBugTitle("");
      setBugDesc("");
      setTimeout(() => { setShowBugReport(false); setBugStatus(null); }, 2000);
    } catch (err) {
      setBugStatus(`Error: ${(err as Error).message}`);
    } finally {
      setBugSubmitting(false);
    }
  }, [bugTitle, bugDesc]);

  return (
    <aside
      className="flex-shrink-0 bg-neutral-bg2 border-r border-border flex flex-col overflow-hidden"
      style={{ ...style, minWidth: 0 }}
    >
      {/* Scrollable content area */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0">

      {/* Top: app branding — logo swaps with active theme */}
      <div className="flex flex-col shrink-0 px-4 py-3 border-b border-border">
        <span className="text-2xl font-bold text-text-primary leading-tight">
          {t("app.brand")}
        </span>
        {theme === "default" ? (
          <div className="flex items-center gap-1 mt-1">
            <img src="/images/foundryiq-logo.png" alt="" className="h-9 w-9 shrink-0" />
            <img src="/images/fabric-logo.png" alt="" className="h-9 w-9 shrink-0" />
            <img src="/images/copilot-logo.png" alt="" className="h-9 w-9 shrink-0" />
          </div>
        ) : (
          <img src={currentMeta.logo} alt="" className="h-9 w-9 shrink-0 mt-1" />
        )}
      </div>

      {/* ── Info section ──────────────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.scenario")}>
        {/* Runtime use-case swap selector (hidden when only one pack exists) */}
        <ScenarioSwitcher />

        {/* Scenario name display */}
        <div className="text-xs text-text-secondary truncate px-1">
          {scenario?.display_name ?? t("common.loading")}
        </div>

        {/* Scenario button */}
        <button
          onClick={() => scenario && setShowScenario(true)}
          className={BTN_DEFAULT}
          title="View scenario details"
        >
          <span className="truncate">{t("sidebar.scenarioDetails")}</span>
        </button>
      </SidebarSection>

      {/* ── Demo replay button ───────────────────────────────────────── */}
      <div className="px-3 py-2">
        <button
          id="demo-flow-button"
          onClick={() => {
            useReplayStore.getState().startReplay("detailed");
            runReplay();
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg
                     bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700
                     text-white text-sm font-semibold shadow-sm
                     transition-colors cursor-pointer"
        >
          <Play className="h-4 w-4 fill-current" />
          {t("sidebar.seeDemo")}
        </button>
        <button
          id="fast-replay-button"
          onClick={() => {
            useReplayStore.getState().startReplay("fast");
            runReplay();
          }}
          className="w-full flex items-center justify-center gap-2 px-3 py-1.5 rounded-lg
                     bg-emerald-600/20 hover:bg-emerald-600/30 active:bg-emerald-600/40
                     text-emerald-400 text-xs font-medium border border-emerald-600/30
                     transition-colors cursor-pointer"
        >
          <Play className="h-3 w-3 fill-current" />
          {t("sidebar.fastReplay")}
        </button>
      </div>

      {/* ── Settings section ─────────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.settings")} collapsible defaultCollapsed>
        <button
          onClick={() => setShowSettings(true)}
          className={`${BTN_DEFAULT} flex items-center gap-2`}
          title={t("sidebar.openSettings")}
        >
          <Settings className="h-4 w-4" />
          <span>{t("sidebar.settings")}</span>
        </button>
      </SidebarSection>

      {/* ── Styles section ─────────────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.styles")} collapsible defaultCollapsed>
        {/* Graph toggle */}
        <button
          onClick={toggleGraph}
          className={graphVisible ? BTN_ACTIVE : BTN_DEFAULT}
          title={graphVisible ? 'Hide graph visualizer' : 'Show graph visualizer'}
        >
          <span className="flex items-center gap-2">
            <img src="/images/graph-icon.png" alt="" className="h-4 w-4" />
            <span className="truncate">{t("sidebar.graph")}</span>
          </span>
        </button>

        {/* UI Scale slider — inline */}
        <div className={`${BTN_DEFAULT} flex flex-col gap-1`}>
          <span className="flex items-center gap-2">
            <Search className="h-4 w-4 shrink-0" />
            <span className="truncate">{t("sidebar.scale")} {Math.round(uiScale * 100)}%</span>
          </span>
          <input
            type="range"
            min={70}
            max={150}
            step={5}
            value={Math.round(uiScale * 100)}
            onChange={(e) => setUiScale(Number(e.target.value) / 100)}
            className="accent-brand cursor-pointer w-full"
            style={{ height: '4px' }}
          />
        </div>

        {/* Chat text size slider — inline */}
        <div className={`${BTN_DEFAULT} flex flex-col gap-1`}>
          <span className="flex items-center gap-2">
            <span>Aa</span>
            <span className="truncate">{t("sidebar.chatText")} {chatTextScale}%</span>
          </span>
          <input
            type="range"
            min={MIN_CHAT_TEXT}
            max={MAX_CHAT_TEXT}
            step={5}
            value={chatTextScale}
            onChange={(e) => setChatTextScale(Number(e.target.value))}
            className="accent-brand cursor-pointer w-full"
            style={{ height: '4px' }}
          />
        </div>

        {/* Theme selector — matches SelectorDropdown style */}
        <HeaderThemeSelector />
      </SidebarSection>

      {/* ── Language section ─────────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.language")} collapsible defaultCollapsed>
        <LanguageSelector />
      </SidebarSection>

      {/* ── Development section ──────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.development")} collapsible defaultCollapsed>
        {/* Console toggle */}
        <button
          onClick={toggleObs}
          className={obsVisible ? BTN_ACTIVE : BTN_DEFAULT}
          title={obsVisible ? 'Hide console panel' : 'Show console panel'}
        >
          <span className="flex items-center gap-2">
            <span>👁</span>
            <span className="truncate">{t("sidebar.console")}</span>
          </span>
        </button>

        {/* Bug Report */}
        <button
          onClick={() => setShowBugReport(!showBugReport)}
          className={`${BTN_DEFAULT} flex items-center gap-2 ${showBugReport ? "text-brand bg-brand/10" : ""}`}
        >
          <Bug className="h-4 w-4" />
          <span>{t("sidebar.reportBug")}</span>
        </button>

        {/* Developer Notes */}
        <button
          onClick={() => setShowDevNotes(!showDevNotes)}
          className={`${BTN_DEFAULT} flex items-center gap-2 ${showDevNotes ? "text-brand bg-brand/10" : ""}`}
        >
          <span>\ud83d\udcdd</span>
          <span>{t("sidebar.developerNotes")}</span>
        </button>

        {/* Debug Questions */}
        <div ref={debugQsRef} className="relative">
          <button
            onClick={() => setShowDebugQs(!showDebugQs)}
            className={`${BTN_DEFAULT} flex items-center gap-2 ${showDebugQs ? "text-brand bg-brand/10" : ""}`}
          >
            <Bug className="h-4 w-4" />
            <span>{t("sidebar.debugQs")}</span>
          </button>
          {showDebugQs && (
            <div className="absolute left-full top-0 ml-2 w-72 max-h-[60vh] overflow-y-auto rounded-xl border border-border bg-neutral-bg2 shadow-2xl z-50">
              {DEBUG_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleDebugSelect(q.prompt)}
                  className={`w-full text-left px-4 py-2.5 text-sm text-text-secondary hover:bg-brand/10 hover:text-text-primary transition-colors ${
                    idx > 0 ? "border-t border-border" : ""
                  }`}
                >
                  <span className="text-text-muted mr-1.5 font-mono text-xs">{idx + 1}.</span>
                  {q.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Session metrics collapsible */}
        <div className="rounded-md border border-border overflow-hidden">
          <button
            onClick={() => setShowDevMetrics((v) => !v)}
            className="w-full px-3 py-2 bg-neutral-bg3 hover:bg-neutral-bg4 transition-colors flex items-center justify-between text-left"
            title={showDevMetrics ? 'Hide session metrics' : 'Show session metrics'}
          >
            <span className="text-sm font-medium text-text-primary">{t("sidebar.sessionMetrics")}</span>
            {showDevMetrics ? (
              <ChevronUp className="h-4 w-4 text-text-muted" />
            ) : (
              <ChevronDown className="h-4 w-4 text-text-muted" />
            )}
          </button>
          {showDevMetrics && (
            <div className="max-h-72 overflow-y-auto bg-neutral-bg2 px-1 py-1">
              <SessionMetrics showHeader={false} />
            </div>
          )}
        </div>

        {/* Bug report form — expanded within development section when active */}
        {showBugReport && (
          <div className="space-y-2 rounded-md border border-border bg-neutral-bg3/50 p-2">
            <input
              value={bugTitle}
              onChange={(e) => setBugTitle(e.target.value)}
              placeholder={t("sidebar.bugReport.title")}
              className="w-full rounded-md bg-neutral-bg1 border border-border px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-brand"
              maxLength={200}
            />
            <textarea
              value={bugDesc}
              onChange={(e) => setBugDesc(e.target.value)}
              placeholder={t("sidebar.bugReport.describe")}
              className="w-full rounded-md bg-neutral-bg1 border border-border px-2 py-1.5 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-brand resize-none"
              rows={3}
              maxLength={5000}
            />
            <div className="flex items-center justify-between gap-2">
              <button
                onClick={handleBugSubmit}
                disabled={bugSubmitting || !bugTitle.trim() || !bugDesc.trim()}
                className="rounded-md bg-brand hover:bg-brand/80 text-white text-xs px-3 py-1.5 font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {bugSubmitting ? t("sidebar.bugReport.sending") : t("sidebar.bugReport.submit")}
              </button>
              {bugStatus && (
                <span className={`text-[10px] truncate ${bugStatus.startsWith("Error") ? "text-status-error" : "text-status-success"}`}>
                  {bugStatus}
                </span>
              )}
            </div>
          </div>
        )}
      </SidebarSection>

      {showDevNotes && (
        <DeveloperNotesOverlay onClose={() => setShowDevNotes(false)} />
      )}

      {showSettings && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowSettings(false)}>
          <div
            className="w-full max-w-xl rounded-2xl border border-border bg-neutral-bg2 shadow-lg"
            role="dialog"
            aria-modal="true"
            aria-label="Settings"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="text-base font-semibold text-text-primary">{t("sidebar.settings")}</h2>
              <button
                onClick={() => setShowSettings(false)}
                className="text-sm text-text-muted hover:text-text-primary transition-colors"
                title={t("common.close")}
              >
                {t("common.close")}
              </button>
            </div>
            <div className="space-y-2 px-4 py-4">
              <div className="rounded-xl border border-border bg-neutral-bg3/40 p-3">
                <p className="text-sm text-text-secondary leading-relaxed">
                  {t("sidebar.settingsNote")}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Service Health section ───────────────────────────────────── */}
      <SidebarSection label={t("health.serviceHealth")} collapsible defaultCollapsed>
        <ServiceHealth showHeader={false} />
      </SidebarSection>

      {/* ── Conversations section ────────────────────────────────────── */}
      <SidebarSection label={t("sidebar.conversations")} collapsible defaultCollapsed>
        <div className="max-h-[22vh] overflow-y-auto -mx-3 -mb-3">
          <ConversationList showHeader={false} />
        </div>
      </SidebarSection>

      {/* ── Fabric capacity note ─────────────────────────────────────── */}
      <div className="px-3 py-2 border-b border-border">
        <div className="p-2 rounded-lg bg-neutral-bg3 border border-border text-sm leading-snug text-text-primary">
          <span className="font-semibold">{t("sidebar.fabricNoteLabel")}</span> {t("sidebar.fabricNote")}
        </div>
      </div>

      </div>{/* end scrollable content area */}

      {/* ── Sticky footer — always visible ──────────────────────────── */}
      <div className="shrink-0 border-t border-border">
        {/* ── User info + logout (auth enabled only) ────────────────── */}
        {isAuthenticated && user && (
          <div className="px-3 py-3 flex items-center gap-2">
            {/* Initials avatar */}
            <div className="w-7 h-7 rounded-full bg-brand text-white text-[10px]
                            flex items-center justify-center font-semibold shrink-0">
              {user.name
                ?.split(" ")
                .map((n) => n[0])
                .join("")
                .slice(0, 2)
                .toUpperCase() || "?"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-text-primary truncate">{user.name}</div>
              <div className="text-[10px] text-text-muted truncate">{user.email}</div>
            </div>
            <div className="flex flex-col gap-0.5 shrink-0">
              <button
                onClick={switchAccount}
                className="text-[10px] text-brand hover:text-text-primary transition-colors"
                title="Switch to a different Microsoft account"
              >
                {t("sidebar.switch")}
              </button>
              <button
                onClick={logout}
                className="text-[10px] text-text-muted hover:text-text-primary transition-colors"
                title={t("sidebar.signOut")}
              >
                {t("sidebar.signOut")}
              </button>
            </div>
          </div>
        )}

        {/* Team affiliation footer */}
        <div className="border-t border-border px-3 py-3">
          <div className="flex items-center gap-2 rounded-md px-2 py-1.5">
            <img src="/gbb-logo.svg" alt="Asia AI Apps GBB logo" className="h-5 w-5 object-contain" />
            <span className="text-sm font-semibold text-text-primary truncate">Asia AI Apps GBB</span>
          </div>
        </div>
      </div>

      {/* Overlay modals — rendered portals, independent of sidebar DOM */}
      {showScenario && scenario && (
        <ScenarioOverlay
          scenario={scenario}
          onClose={() => setShowScenario(false)}
        />
      )}

    </aside>
  );
}

function SidebarSection({
  label,
  children,
  collapsible = false,
  defaultCollapsed = false,
}: {
  label: string;
  children: React.ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="border-b border-border">
      <div className="px-3 pt-3 pb-1">
        {collapsible ? (
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="w-full flex items-center justify-between text-left"
            title={collapsed ? `Expand ${label}` : `Collapse ${label}`}
          >
            <span className="text-xs uppercase tracking-widest font-semibold text-text-muted">{label}</span>
            {collapsed ? (
              <ChevronDown className="h-4 w-4 text-text-muted" />
            ) : (
              <ChevronUp className="h-4 w-4 text-text-muted" />
            )}
          </button>
        ) : (
          <span className="text-xs uppercase tracking-widest font-semibold text-text-muted">{label}</span>
        )}
      </div>
      {!collapsed && <div className="flex flex-col gap-1.5 px-3 pb-3">{children}</div>}
    </div>
  );
}

/** Theme selector — uses SelectorDropdown style, swaps UI theme + logo. */
function HeaderThemeSelector() {
  const { theme, setTheme } = useTheme();

  /* Adapt THEMES array to SelectorDropdown's generic interface */
  const items = THEMES.map((t) => ({ ...t, is_active: t.id === theme }));

  return (
    <SelectorDropdown
      label="UI Theme"
      items={items}
      activeId={theme}
      getItemId={(t) => t.id}
      getItemLabel={(t) => `${t.icon} ${t.label}`}
      onSwitch={(id) => setTheme(id as typeof theme)}
      switching={false}
      error={null}
    />
  );
}

/** Language selector — dropdown that switches all UI text to another locale. */
function LanguageSelector() {
  const locale = useLocaleStore((s) => s.locale);
  const setLocale = useLocaleStore((s) => s.setLocale);

  return (
    <div className="text-sm w-full px-3 py-2 rounded-md border border-border bg-neutral-bg3/70 text-text-primary">
      <div className="flex items-center gap-2">
        <span className="shrink-0">🌐</span>
        <select
          value={locale}
          onChange={(e) => setLocale(e.target.value as typeof locale)}
          className="flex-1 bg-transparent text-text-primary text-sm outline-none cursor-pointer"
        >
          {SUPPORTED_LOCALES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

