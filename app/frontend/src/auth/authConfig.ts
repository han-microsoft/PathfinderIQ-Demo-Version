/**
 * MSAL configuration — fetches auth settings from the backend.
 *
 * Module role:
 *   Fetches GET /api/auth_setup from the backend to determine whether auth
 *   is enabled and what the MSAL configuration should be. Exports the resolved
 *   config + PublicClientApplication singleton.
 *
 *   When useLogin=false (dev mode), msalInstance is null and no MSAL code
 *   runs at all — zero impact on the dev experience.
 *
 * Key collaborators:
 *   - main.py /api/auth_setup endpoint — provides config
 *   - AuthProvider.tsx — consumes msalInstance
 *   - useAuth.ts — acquires tokens via msalInstance
 *
 * Dependents:
 *   Called by: main.tsx (initAuth), client.ts (getAccessToken)
 */

import {
  type Configuration,
  PublicClientApplication,
  EventType,
} from "@azure/msal-browser";
import type { AuthSetupResponse } from "../api/types";
import { BASE } from "@/foundation/constants";

/* Resolved auth configuration from /api/auth_setup. Set by initAuth(). */
export let authSetup: AuthSetupResponse = { useLogin: false };

/* MSAL PublicClientApplication singleton. Null when auth is disabled. */
export let msalInstance: PublicClientApplication | null = null;

/**
 * Initialise the auth system by fetching backend config.
 *
 * Must be called once before React renders. When useLogin=false, this is
 * a fast no-op (one fetch, no MSAL). When useLogin=true, initialises
 * MSAL with the backend-provided clientId/authority/scopes.
 *
 * Side effects:
 *   - Sets module-level authSetup and msalInstance
 *   - MSAL subscribes to LOGIN_SUCCESS events (set active account)
 *   - Console logs for observability panel ([auth] prefix)
 */
export async function initAuth(): Promise<void> {
  try {
    const res = await fetch(`${BASE}/auth_setup`);
    authSetup = await res.json();
  } catch (err) {
    /* If the backend is unreachable, fall back to no-auth mode.
       This prevents the frontend from crashing on startup when
       running without a backend (e.g. static preview). */
    console.warn("[auth] Failed to fetch /api/auth_setup, defaulting to no-auth:", err);
    authSetup = { useLogin: false };
  }

  console.info("[auth] initAuth: useLogin=%s", authSetup.useLogin);

  if (!authSetup.useLogin) {
    msalInstance = null;
    return;
  }

  /* Build MSAL config following azure-search-openai-demo pattern.
     cacheLocation=localStorage enables SSO across browser tabs —
     user logs in once, all tabs are authenticated. */
  const msalConfig: Configuration = {
    auth: {
      clientId: authSetup.clientId!,
      authority: authSetup.authority!,
      redirectUri: window.location.origin,
      postLogoutRedirectUri: window.location.origin,
    },
    cache: {
      cacheLocation: "localStorage",
      storeAuthStateInCookie: false,
    },
  };

  msalInstance = new PublicClientApplication(msalConfig);
  await msalInstance.initialize();

  /* Set active account from cached accounts (enables tab-SSO).
     If user previously logged in and localStorage has cached tokens,
     MSAL restores the session without a redirect. */
  const accounts = msalInstance.getAllAccounts();
  if (accounts.length > 0 && !msalInstance.getActiveAccount()) {
    msalInstance.setActiveAccount(accounts[0]);
  }

  /* Subscribe to login success events — update active account when
     user completes a login popup/redirect flow. */
  msalInstance.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
      const payload = event.payload as { account?: { username?: string } };
      if (payload.account) {
        msalInstance!.setActiveAccount(payload.account as ReturnType<PublicClientApplication["getActiveAccount"]>);
        console.info("[auth] user authenticated: %s", payload.account.username);
      }
    }
  });

  console.info("[auth] MSAL initialized, %d cached accounts", accounts.length);
}
