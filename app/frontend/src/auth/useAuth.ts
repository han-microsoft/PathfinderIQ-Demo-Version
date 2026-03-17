/**
 * useAuth — React hook + standalone getAccessToken for auth state.
 *
 * Module role:
 *   Provides both a React hook (useAuth) for components that need auth
 *   state, and a standalone async function (getAccessToken) for the API
 *   client (client.ts) which runs outside React's component tree.
 *
 *   When auth is disabled: useAuth returns unauthenticated defaults,
 *   getAccessToken returns null. No MSAL calls, no popups.
 *
 * Key collaborators:
 *   - authConfig.ts — msalInstance and authSetup
 *   - client.ts — calls getAccessToken() for Bearer header
 *   - Header.tsx — calls useAuth() for user info + logout
 *   - AuthProvider.tsx — renders LoginScreen based on auth state
 *
 * Dependents:
 *   Called by: client.ts (getAccessToken), Header.tsx (useAuth)
 */

import { useMsal } from "@azure/msal-react";
import { authSetup, msalInstance } from "./authConfig";

/**
 * Acquire an access token for API calls.
 *
 * Standalone async function (not a hook) — callable from client.ts
 * which is not inside React's component tree.
 *
 * Strategy:
 *   1. Try acquireTokenSilent (uses cached/refreshed token — instant)
 *   2. On failure, fall back to acquireTokenPopup (interactive login)
 *   3. On failure, return null (API call will get 401 from backend)
 *
 * When auth is disabled: returns null immediately (no MSAL calls).
 *
 * @returns Access token string, or null if auth is disabled / failed.
 */
export async function getAccessToken(): Promise<string | null> {
  if (!msalInstance || !authSetup.useLogin) return null;

  const account = msalInstance.getActiveAccount();
  if (!account) return null;

  try {
    const response = await msalInstance.acquireTokenSilent({
      scopes: authSetup.scopes!,
      account,
    });
    console.debug("[auth] acquireTokenSilent succeeded");
    return response.accessToken;
  } catch {
    /* Silent renewal failed — cached token expired and iframe refresh
       didn't work (e.g. user's Entra session expired). Fall back to
       interactive popup so user can re-authenticate. */
    console.warn("[auth] acquireTokenSilent failed, falling back to popup");
    try {
      const response = await msalInstance.acquireTokenPopup({
        scopes: authSetup.scopes!,
      });
      return response.accessToken;
    } catch (popupErr) {
      console.error("[auth] acquireTokenPopup failed:", popupErr);
      return null;
    }
  }
}

/**
 * React hook for authentication state.
 *
 * Returns:
 *   isAuthenticated — true if user has an active MSAL account
 *   user — { name, email } from the active account, or null
 *   logout — function to trigger MSAL popup logout
 *
 * When auth is disabled: isAuthenticated=false, user=null, logout=noop.
 */
export function useAuth() {
  if (!msalInstance || !authSetup.useLogin) {
    /* Auth disabled — return inert defaults. No MSAL hooks called. */
    return {
      isAuthenticated: false as const,
      user: null as { name: string; email: string } | null,
      logout: () => {},
      switchAccount: () => {},
    };
  }

  /* useMsal() is only callable within MsalProvider — which AuthProvider
     ensures is rendered when auth is enabled. */
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const { accounts, instance } = useMsal();
  const isAuthenticated = accounts.length > 0;
  const activeAccount = instance.getActiveAccount();

  const user = activeAccount
    ? {
        name: activeAccount.name ?? "",
        email: activeAccount.username ?? "",
      }
    : null;

  const logout = () => {
    console.info("[auth] user logged out");
    instance.logoutPopup();
  };

  /** Switch to a different Microsoft account via interactive popup. */
  const switchAccount = async () => {
    console.info("[auth] switching account");
    try {
      const response = await instance.loginPopup({
        scopes: authSetup.scopes!,
        prompt: "select_account",
      });
      if (response.account) {
        instance.setActiveAccount(response.account);
        console.info("[auth] switched to", response.account.username);
        // Reload to re-fetch user-scoped data (sessions, config)
        window.location.reload();
      }
    } catch (err) {
      console.error("[auth] account switch failed:", err);
    }
  };

  return { isAuthenticated, user, logout, switchAccount };
}
