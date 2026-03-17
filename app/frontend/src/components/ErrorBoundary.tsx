/**
 * Top-level error boundary — prevents full-app white-screen crashes.
 *
 * Module role:
 *   Catches unhandled React render errors anywhere in the component tree
 *   and displays a recovery UI instead of a blank white screen. The user
 *   can click "Reload" to recover.
 *
 * Key collaborators:
 *   - main.tsx — wraps <App /> with this boundary
 *
 * Dependents:
 *   Used by: main.tsx (sole consumer)
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * React class component error boundary.
 * Functional components cannot catch render errors — class components
 * with componentDidCatch are the only mechanism React provides.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log to console (will be captured by consoleInterceptor if installed)
    console.error("[ErrorBoundary] Unhandled render error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100vh",
            fontFamily: "system-ui, sans-serif",
            padding: "2rem",
            textAlign: "center",
            backgroundColor: "#1a1a2e",
            color: "#e0e0e0",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", marginBottom: "1rem" }}>
            Something went wrong
          </h1>
          <p style={{ color: "#999", marginBottom: "1.5rem", maxWidth: "400px" }}>
            An unexpected error occurred. Click below to reload the application.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: "0.75rem 1.5rem",
              fontSize: "1rem",
              borderRadius: "0.5rem",
              border: "none",
              backgroundColor: "#3b82f6",
              color: "white",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
          {this.state.error && (
            <pre
              style={{
                marginTop: "2rem",
                padding: "1rem",
                background: "#0d0d1a",
                borderRadius: "0.5rem",
                fontSize: "0.75rem",
                color: "#888",
                maxWidth: "600px",
                overflow: "auto",
                textAlign: "left",
              }}
            >
              {this.state.error.message}
            </pre>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
