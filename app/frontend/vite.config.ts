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
  build: {
    // Split heavy vendors into separate, parallel-loadable, cacheable chunks
    // so the entry bundle stays small (faster first paint of the demo landing).
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("react-force-graph") || id.includes("force-graph") || id.includes("/d3")) return "graph";
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
