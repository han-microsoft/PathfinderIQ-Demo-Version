/**
 * Auth module barrel export.
 *
 * Re-exports public API from auth submodules for clean imports:
 *   import { AuthProvider, useAuth, getAccessToken, initAuth } from "./auth";
 */

export { AuthProvider } from "./AuthProvider";
export { useAuth, getAccessToken } from "./useAuth";
export { authSetup, msalInstance, initAuth } from "./authConfig";
