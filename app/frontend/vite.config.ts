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
      "@agentkit-ui": path.resolve(__dirname, "./packages/agentkit-ui/src"),
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
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: "http://localhost:9000", changeOrigin: true },
      "/health": { target: "http://localhost:9000", changeOrigin: true },
    },
  },
  build: {
    // Split heavy vendors into separate, parallel-loadable, cacheable chunks
    // so the entry bundle stays small (faster first paint of the demo landing).
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          // Let Rollup co-locate react-force-graph + d3 in the lazy MetricsBar
          // async chunk (return undefined) instead of forcing them into a
          // manual chunk. Forcing the grouping created an intra-chunk
          // circular-init TDZ ("Cannot access 'X' before initialization") in
          // the production bundle; natural chunking orders their init safely
          // AND keeps them out of the eager first-paint bundle.
          if (id.includes("react-force-graph") || id.includes("force-graph") || id.includes("/d3")) return undefined;
          if (id.includes("react-syntax-highlighter") || id.includes("refractor") || id.includes("prismjs") || id.includes("highlight.js")) return "syntax";
          if (id.includes("framer-motion")) return "motion";
          if (id.includes("react-markdown") || id.includes("remark") || id.includes("micromark") || id.includes("mdast") || id.includes("hast") || id.includes("unist") || id.includes("vfile")) return "markdown";
          if (id.includes("@azure/msal")) return "msal";
          if (id.includes("react-day-picker") || id.includes("date-fns")) return "datepicker";
          return "vendor";
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
