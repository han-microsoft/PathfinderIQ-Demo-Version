/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "selector",
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Segoe UI Variable"', '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
      colors: {
        brand: {
          DEFAULT: "var(--color-brand)",
          hover: "var(--color-brand-hover)",
          light: "var(--color-brand-light)",
          subtle: "var(--color-brand-subtle)",
        },
        neutral: {
          bg1: "var(--color-bg-1)",
          bg2: "var(--color-bg-2)",
          bg3: "var(--color-bg-3)",
          bg4: "var(--color-bg-4)",
          bg5: "var(--color-bg-5)",
          bg6: "var(--color-bg-6)",
        },
        text: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          muted: "var(--color-text-muted)",
          tertiary: "var(--color-text-tertiary)",
        },
        border: {
          subtle: "var(--color-border-subtle)",
          DEFAULT: "var(--color-border-default)",
          strong: "var(--color-border-strong)",
        },
        status: {
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
          info: "var(--color-info)",
        },
        header: {
          bg: "var(--color-header-bg)",
          text: "var(--color-header-text)",
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 1.4s infinite ease-in-out both",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: "0.4" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
