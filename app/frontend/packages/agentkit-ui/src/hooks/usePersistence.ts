/**
 * usePersistence — mirror selected UI state to localStorage.
 *
 * Strategy:
 *   We avoid running the Zustand `persist` middleware on panelStore because
 *   some fields (pinnedSituation: a full SituationRecord) are derived from
 *   API responses and would rehydrate into stale references after a
 *   backend schema change. Instead, this hook persists only operator
 *   preferences that are safe across scans.
 *
 *   Currently the hook is also the one-shot cleanup site for retired
 *   localStorage keys so stale browser state never lingers.
 *
 * 2026-05-18 — centre-tab persistence retired. Operator brief: Priorities
 * should always be the landing surface on fresh load, regardless of which
 * mode was last visited in a previous session. The panelStore default of
 * `centerTab: "priorities"` now wins on every mount. The previous
 * `gridiq:centerTab` key is purged on first mount of this hook so
 * browsers carrying stale state don't override the new default. The
 * subscribe-and-mirror loop has been removed; mode switches during a
 * session live only in memory.
 */

import { useEffect } from "react";

/** Retired key — was `gridiq:centerTab`. Purged on first mount so
 *  Priorities reliably wins the fresh-load default. The constant can be
 *  deleted once we are confident no operator browser still holds it. */
const RETIRED_KEY_CENTER_TAB = "gridiq:centerTab";

/** Legacy key from the short-lived chat-first / workspace-toggle experiment
 *  (Couturier v2 R1). The toggle was retired — workspace is always open —
 *  so we purge the persisted value on first mount to avoid carrying dead
 *  state across releases. */
const LEGACY_KEY_WORKSPACE_EXPANDED = "gridiq:workspaceExpanded";

export function usePersistence() {
  /* One-shot cleanup of retired/legacy localStorage keys. No hydration,
     no subscribe — the centre-tab default is the panelStore default. */
  useEffect(() => {
    try {
      window.localStorage.removeItem(RETIRED_KEY_CENTER_TAB);
      window.localStorage.removeItem(LEGACY_KEY_WORKSPACE_EXPANDED);
    } catch {
      /* localStorage may be unavailable (private mode, quota); the
         in-memory store defaults stand without it. */
    }
  }, []);
}
