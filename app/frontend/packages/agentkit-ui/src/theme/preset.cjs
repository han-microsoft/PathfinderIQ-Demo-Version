/**
 * agentkit-ui — Tailwind preset (the central, shippable style contract).
 *
 * This preset carries the DOMAIN-BLIND design system the extracted
 * components depend on: the font-size scale, font families, the generic
 * semantic colour groups (brand / neutral / text / border / status /
 * overlay / header / section / teams / …), and the pulse-dot animation.
 * Every value resolves to a `var(--color-*)` / `var(--font-*)` CSS token,
 * so a consumer themes the whole kit by defining those vars in its own
 * `tokens.css` (see ./tokens.css for the contract + neutral defaults).
 *
 * Consumer usage (host app tailwind.config.js):
 *   module.exports = {
 *     content: [...],                       // include packages/agentkit-ui/src
 *     presets: [require("@agentkit/ui/theme/preset")],
 *     theme: { extend: { colors: { ...domain-specific groups } } },
 *   };
 *
 * Domain-specific colour groups (priority / severity / watcher /
 * situation / delegation / tag / sim in GridIQ) stay in the consumer's
 * own config — they are NOT part of the reusable kit.
 */
module.exports = {
  theme: {
    /* Font-size scale — centralised via CSS vars from the token contract. */
    fontSize: {
      micro: ["var(--font-size-micro)", { lineHeight: "1rem" }],
      label: ["var(--font-size-label)", { lineHeight: "1rem" }],
      xs: ["var(--font-size-xs)", { lineHeight: "1rem" }],
      sm: ["var(--font-size-sm)", { lineHeight: "1.25rem" }],
      base: ["var(--font-size-base)", { lineHeight: "1.5rem" }],
      lg: ["var(--font-size-lg)", { lineHeight: "1.75rem" }],
      xl: ["var(--font-size-xl)", { lineHeight: "1.75rem" }],
      display: ["var(--font-size-display)", { lineHeight: "1.75rem" }],
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
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
        divider: "var(--color-divider)",
        status: {
          success: "var(--color-success)",
          warning: "var(--color-warning)",
          error: "var(--color-error)",
          info: "var(--color-info)",
          "success-surface": "var(--color-success-surface)",
          "warning-surface": "var(--color-warning-surface)",
          "error-surface": "var(--color-error-surface)",
          "info-surface": "var(--color-info-surface)",
        },
        header: {
          bg: "var(--color-header-bg)",
          text: "var(--color-header-text)",
          border: "var(--color-header-border)",
        },
        app: {
          bg: "var(--color-bg-app)",
        },
        "center-panel": {
          bg: "var(--color-bg-center-panel)",
        },
        on: {
          accent: "var(--color-on-accent)",
        },
        placeholder: {
          DEFAULT: "var(--color-placeholder)",
        },
        section: {
          "gradient-from": "var(--color-section-gradient-from)",
          "gradient-via": "var(--color-section-gradient-via)",
          "gradient-hover": "var(--color-section-gradient-hover)",
          label: "var(--color-section-label)",
          indicator: "var(--color-section-indicator)",
          empty: "var(--color-section-empty)",
        },
        subsection: {
          "gradient-from": "var(--color-subsection-gradient-from)",
          "gradient-via": "var(--color-subsection-gradient-via)",
          "gradient-hover": "var(--color-subsection-gradient-hover)",
        },
        overlay: {
          bg: "var(--color-overlay-bg)",
          border: "var(--color-overlay-border)",
          hover: "var(--color-overlay-hover)",
          "backdrop-light": "var(--color-overlay-backdrop-light)",
          backdrop: "var(--color-overlay-backdrop)",
          "backdrop-heavy": "var(--color-overlay-backdrop-heavy)",
        },
        "error-page": {
          bg: "var(--color-error-page-bg)",
          text: "var(--color-error-page-text)",
          secondary: "var(--color-error-page-secondary)",
          "button-bg": "var(--color-error-page-button-bg)",
          "code-bg": "var(--color-error-page-code-bg)",
          "code-text": "var(--color-error-page-code-text)",
        },
        teams: {
          backdrop: "var(--color-teams-backdrop)",
          avatar: "var(--color-teams-avatar)",
          status: "var(--color-teams-status)",
          text: "var(--color-teams-text)",
          "text-muted": "var(--color-teams-text-muted)",
          "control-bg": "var(--color-teams-control-bg)",
          "control-hover": "var(--color-teams-control-hov)",
          mute: "var(--color-teams-mute)",
          "mute-hover": "var(--color-teams-mute-hover)",
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
  plugins: [
    require("@tailwindcss/typography"),
    /* Container queries: lets a kit consumer reflow card head rows as the
       surrounding resizable column narrows (viewport breakpoints are
       useless when only the panel resizes, not the viewport). */
    require("@tailwindcss/container-queries"),
  ],
};
