/**
 * AuthProvider — conditional MSAL wrapper + login gate.
 *
 * Module role:
 *   If auth is disabled (useLogin=false): renders children directly.
 *   No MsalProvider, no MSAL hooks, no login screen.
 *
 *   If auth is enabled:
 *     - Wraps children in MsalProvider from @azure/msal-react
 *     - Shows LoginScreen if user is not yet authenticated
 *     - Shows children (App) once user is authenticated
 *
 * Key collaborators:
 *   - authConfig.ts — authSetup.useLogin and msalInstance
 *   - LoginScreen.tsx — shown before login
 *   - App.tsx — shown after login (passed as children)
 *
 * Dependents:
 *   Wrapped around <App /> in main.tsx
 */

import type { ReactNode } from "react";
import { MsalProvider } from "@azure/msal-react";
import { useMsal } from "@azure/msal-react";
import { authSetup, msalInstance } from "./authConfig";
import { LoginScreen } from "./LoginScreen";

/**
 * Top-level auth wrapper. Renders one of:
 *   - Children directly (auth disabled — dev mode)
 *   - MsalProvider > AuthGate > children (auth enabled)
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  if (!authSetup.useLogin || !msalInstance) {
    /* Dev mode — render app directly, no auth, no MSAL overhead */
    return <>{children}</>;
  }

  return (
    <MsalProvider instance={msalInstance}>
      <AuthGate>{children}</AuthGate>
    </MsalProvider>
  );
}

/**
 * Auth gate — controls visibility based on authentication state.
 *
 * Shows LoginScreen when no accounts are present in MSAL.
 * Shows children (the app) when at least one account is authenticated.
 *
 * Must be rendered inside MsalProvider.
 */
function AuthGate({ children }: { children: ReactNode }) {
  const { accounts } = useMsal();
  const isAuthenticated = accounts.length > 0;

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  return <>{children}</>;
}
