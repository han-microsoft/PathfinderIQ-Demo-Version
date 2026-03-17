/**
 * Vite configuration — React dev server and production bundler.
 *
 * Path alias: `@/` maps to `src/` for clean imports.
 * Dev server runs on port 5173 (matches CORS_ORIGINS in backend config).
 * React plugin enables Fast Refresh for hot module replacement.
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:9000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:9000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
