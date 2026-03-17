/**
 * LoginScreen — full-screen "Sign in with Microsoft" gate.
 *
 * Module role:
 *   Shown when auth is enabled but the user has not logged in.
 *   Presents a centred card with the app title and a login button.
 *   Calls msalInstance.loginPopup() to trigger the Entra ID flow.
 *
 * Key collaborators:
 *   - AuthProvider.tsx — conditionally renders this component
 *   - authConfig.ts — authSetup.scopes used for loginPopup request
 *
 * Dependents:
 *   Rendered by: AuthProvider.AuthGate (when isAuthenticated=false)
 */

import { useState } from "react";
import { useMsal } from "@azure/msal-react";
import { authSetup } from "./authConfig";

export function LoginScreen() {
  const { instance } = useMsal();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    console.info("[auth] login popup initiated");

    try {
      await instance.loginPopup({
        scopes: authSetup.scopes ?? [],
      });
      /* After successful login, MsalProvider detects the new account
         and AuthGate re-renders → shows the app. */
    } catch (err) {
      const message = (err as Error).message ?? "Login failed";
      console.error("[auth] login failed: %s", message);
      setError(message);
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center h-screen w-screen bg-neutral-bg1">
      <div className="flex flex-col items-center gap-6 p-10 rounded-xl border border-border bg-neutral-bg2 shadow-lg max-w-sm w-full">
        {/* App branding */}
        <div className="flex items-center gap-3">
          <img src="/images/fabric-logo.png" alt="" className="h-10 w-10" />
          <h1 className="text-xl font-bold text-text-primary">
            3IQ — Azure Native Agentic Graphs
          </h1>
        </div>

        <p className="text-sm text-text-muted text-center">
          Sign in with your Microsoft account to continue.
        </p>

        {/* Sign in button */}
        <button
          onClick={handleLogin}
          disabled={loading}
          className={[
            "flex items-center justify-center gap-2 w-full py-2.5 px-4",
            "rounded-lg font-medium text-sm transition-colors",
            "bg-brand hover:bg-brand-hover text-white",
            "disabled:opacity-50 disabled:cursor-wait",
          ].join(" ")}
        >
          {loading ? (
            <>
              {/* Spinner */}
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12" cy="12" r="10"
                  stroke="currentColor" strokeWidth="4" fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Signing in…
            </>
          ) : (
            <>
              {/* Microsoft logo */}
              <svg className="h-4 w-4" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
                <rect x="1" y="1" width="9" height="9" fill="#f25022" />
                <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
                <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
                <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
              </svg>
              Sign in with Microsoft
            </>
          )}
        </button>

        {/* Error message */}
        {error && (
          <p className="text-xs text-status-error text-center max-w-full break-words">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
