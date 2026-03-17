/**
 * Application entry point — mounts the React app to the DOM.
 *
 * Module role:
 *   Creates the React root, wraps the App component in StrictMode (enables
 *   development-only checks) and ThemeProvider (light/dark mode), and imports
 *   global CSS (Tailwind base + custom theme tokens).
 *
 * Render target: <div id="root"> in index.html
 *
 * Key collaborators:
 *   - App.tsx          — the application shell
 *   - ThemeContext.tsx  — light/dark mode state
 *   - index.css         — Tailwind base + CSS custom properties
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ThemeProvider } from "./ThemeContext";
import { AuthProvider, initAuth } from "./auth";
import "./index.css";
import { installConsoleInterceptor } from "./utils/consoleInterceptor";

/* Install console interceptor before React renders so all console.* output
   (including React warnings, component logs, etc.) is captured and forwarded
   to the Backend observability endpoint for the Frontend log tab. */
installConsoleInterceptor();

/* Initialise auth before React renders.
   Wrapped in async IIFE — top-level await requires build.target="esnext"
   in vite.config.ts which the project does not currently set.
   When AUTH_ENABLED=false, initAuth() is a fast no-op (one fetch). */
(async () => {
  await initAuth();

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ThemeProvider>
      </ErrorBoundary>
    </StrictMode>,
  );
})();
