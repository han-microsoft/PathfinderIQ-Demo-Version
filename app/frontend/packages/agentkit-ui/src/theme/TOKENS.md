# Token contract — @agentkit/ui

The kit's Tailwind preset (`preset.cjs`) maps every visual to a CSS variable. The kit **ships default values** for all of them in [`tokens.css`](tokens.css) (a self-contained neutral dark theme) — import it once and everything renders:

```css
@import "@agentkit/ui/theme/tokens.css";   /* defaults */
@import "./my-overrides.css";              /* optional: redefine any --color-* / --font-* */
```

To re-theme (light mode, brand colours), redefine the var in a stylesheet loaded **after** the default. The table below is the contract: var names are stable; values are yours to override. (GridIQ ships its own `app/frontend/src/theme/tokens.css` instead of the kit default, adding domain groups on top.)

## Typography
- `--font-sans`, `--font-mono`
- `--font-size-micro|label|xs|sm|base|lg|xl|display`

## Generic colour groups (owned by the preset)
| Tailwind group | CSS vars |
|---|---|
| `brand` | `--color-brand`, `--color-brand-hover`, `--color-brand-light`, `--color-brand-subtle` |
| `neutral` | `--color-bg-1` … `--color-bg-6` |
| `text` | `--color-text-primary|secondary|muted|tertiary` |
| `border` | `--color-border-subtle|default|strong` |
| `divider` | `--color-divider` |
| `status` | `--color-success|warning|error|info` (+ `-surface` variants) |
| `header` | `--color-header-bg|text|border` |
| `app` / `center-panel` | `--color-bg-app`, `--color-bg-center-panel` |
| `on` | `--color-on-accent` |
| `placeholder` | `--color-placeholder` |
| `section` / `subsection` | `--color-section-*`, `--color-subsection-*` |
| `overlay` | `--color-overlay-bg|border|hover|backdrop|backdrop-light|backdrop-heavy` |
| `error-page` | `--color-error-page-*` |
| `teams` | `--color-teams-*` (consumed by `TeamsCallModal`) |

## Animation
- `pulse-dot` keyframes (used by `StreamingIndicator`) — defined in the preset, no token needed.

## Animation contract (consumer-supplied global CSS)
Some `feedback` components reference global animation classes/keyframes the consumer must define in its own `index.css` (same model as the colour tokens — the kit references by name, the consumer supplies). GridIQ defines these in `app/frontend/src/index.css`.
- `--motion-ease` (token) + `fade-in` keyframe — `Toaster` enter animation (`animate-[fade-in_150ms_var(--motion-ease)]`).
- `animate-fade-in`, `animate-spin-slow` — `CountdownPill`.
- A consumer "fresh/pulse" highlight class is **injected** (`Toaster pulseClassName`), so no fixed contract — GridIQ passes `animate-fresh-hairline`.

## Prose-scaling allowlist (intentional, not a token violation)
`MarkdownRenderer` uses em-relative sizing (`text-[inherit]`, `text-[0.85em]`, `text-[0.7em]`) so markdown content scales with its container's font-size. This is correct for prose and is exempt from the token-discipline lint.

## Domain tokens (NOT part of the kit)
GridIQ's `priority` / `severity` / `watcher` / `situation` / `delegation` / `tag` / `sim` colour groups + their `--color-*` vars live in the consumer's own `tailwind.config.js` + `tokens.css`. The kit neither defines nor depends on them.
