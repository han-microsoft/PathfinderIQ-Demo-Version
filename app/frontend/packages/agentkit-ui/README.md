# @agentkit/ui — reusable, domain-blind React component kit

A drop-in React component kit: streaming-chat scaffolding, overlays, hooks, stores, HTTP + SSE helpers, a layout shell, and a fully-tokenised theme. **Every visual is driven from a central Tailwind preset + CSS-var token contract — zero hardcoded colour/size values** — so you re-skin the whole kit by changing CSS variables, not component code.

Extracted from GridIQ (a control-room app) as "Tier-2". GridIQ is the first consumer, not the owner: the kit imports **no** consumer store, API client, or domain type. Delete every GridIQ feature and the kit still stands; delete the kit and only the generic primitives break (never the domain features).

> **Audience: humans and coding agents.** This README is the single source of truth for *using*, *theming*, and *extending* the kit. Read [§7 Extending the kit](#7-extending-the-kit) before adding or modifying anything.

---

## Table of contents

1. [Quickstart (drop into a new project)](#1-quickstart-drop-into-a-new-project)
2. [How it's wired in this repo (the alias)](#2-how-its-wired-in-this-repo-the-alias)
3. [Architecture & layering](#3-architecture--layering)
4. [The composition pattern (engine vs binding)](#4-the-composition-pattern-engine-vs-binding)
5. [API reference (per subpath)](#5-api-reference-per-subpath)
6. [Theming](#6-theming)
7. [Extending the kit](#7-extending-the-kit)
8. [Discipline & verification](#8-discipline--verification)
9. [Gotchas / FAQ](#9-gotchas--faq)
10. [Roadmap](#10-roadmap)

---

## 1. Quickstart (drop into a new project)

The kit is a **source package** (no build step, no publish). You consume its TypeScript directly via a path alias. Four wiring steps, then import.

**Step 1 — peer deps.** Install what your project uses (all are peers, none bundled):

```bash
npm i react react-dom lucide-react react-markdown remark-gfm \
      react-syntax-highlighter react-day-picker date-fns zustand react-resizable-panels
```

Only the deps for the subpaths you import are required (e.g. you can skip `react-resizable-panels` if you never import `@agentkit-ui/layout`).

**Step 2 — path alias.** Point `@agentkit-ui/*` at the package source in BOTH places (TS resolves one way, the bundler another — both must agree):

```jsonc
// tsconfig.json
{ "compilerOptions": { "paths": {
  "@agentkit-ui": ["packages/agentkit-ui/src"],
  "@agentkit-ui/*": ["packages/agentkit-ui/src/*"]
}}, "include": ["src", "packages/agentkit-ui/src"] }
```

```ts
// vite.config.ts  — more-specific alias FIRST so "@" never swallows "@agentkit-ui/…"
resolve: { alias: {
  "@agentkit-ui": path.resolve(__dirname, "./packages/agentkit-ui/src"),
  "@": path.resolve(__dirname, "./src"),
}}
```

**Step 3 — Tailwind preset + scan path.** Extend the preset and add the kit source to `content` (or its classes get purged):

```js
// tailwind.config.js
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}", "./packages/agentkit-ui/src/**/*.{ts,tsx}"],
  presets: [require("./packages/agentkit-ui/src/theme/preset.cjs")],
  theme: { extend: { colors: { /* your DOMAIN colour groups only */ } } },
};
```

**Step 4 — global CSS (tokens + animations).** Import the kit's default theme + motion once. The defaults render a complete neutral dark theme out of the box; override any var afterwards.

```css
/* src/index.css */
@import "@agentkit/ui/theme/tokens.css";      /* default palette + fonts (self-contained) */
@import "@agentkit/ui/theme/animations.css";  /* fade-in / spin-slow / fresh-hairline / … */
/* @import "./my-overrides.css";              optional: re-theme by redefining --color-* */
```

**Done — import and render:**

```tsx
import { MarkdownRenderer, ErrorBoundary } from "@agentkit-ui/primitives";
import { ToolResultCard, ResultTable } from "@agentkit-ui/chat";
import { useToastStore } from "@agentkit-ui/stores";
import { Toaster } from "@agentkit-ui/feedback";
import { parseSSEStream } from "@agentkit-ui/sse";

function App() {
  const { toasts, dismissToast } = useToastStore();
  return (
    <ErrorBoundary>
      <ToolResultCard scope={[{ label: "id", value: "42" }]} signal={[{ label: "rows", value: 3 }]}>
        <MarkdownRenderer content="**hello** kit" />
      </ToolResultCard>
      <Toaster toasts={toasts} onDismiss={dismissToast} />
    </ErrorBoundary>
  );
}
```

---

## 2. How it's wired in this repo (the alias)

In GridIQ the package lives at `app/frontend/packages/agentkit-ui/`. It sits **inside** `app/frontend/` deliberately so it stays in the Docker frontend build context (`COPY app/frontend/ .`). There is no separate build/publish step — `tsc`/Vite compile the package source as part of the app, resolving `@agentkit-ui/*` through the alias (tsconfig `paths` + vite `resolve.alias`). The `exports` map in `package.json` documents the public surface; **resolution is via the alias, not that field**.

To extract the kit to a standalone npm package later: keep the same `src/` layout, add a Vite library build + `tsc` declaration emit, and the `exports` map already describes the entry points.

---

## 3. Architecture & layering

```
@agentkit-ui/
  theme/        preset.cjs (Tailwind) · tokens.css (default vars) · animations.css · TOKENS.md
  foundation/   pure vocabulary + helpers (severity ranking/bucket)        — zero deps
  http/         ApiError · parseResponse · auth-SDK-agnostic helpers        — zero deps
  hooks/        useAutoScroll · usePersistence · useTypewriter ·
                useKeydownDispatcher · useOutsideClick · useDebouncedValue   — react only
  stores/       toastStore · paletteStore                                    — zustand
  primitives/   MarkdownRenderer · DateRangePicker · ValueDial ·
                TeamsCallModal · StreamingIndicator · normalizeBullets ·
                ErrorBoundary                                                — react + peer libs
  sse/          parseSSEStream (wire decode loop)                           — zero deps
  feedback/     Toaster · HelpOverlay · CountdownPill ·
                CommandPaletteBase · TimedProgress(Bar|Panel)               — react + lucide
  chat/         ToolResultCard · ResultTable · ArgumentsGrid ·
                JsonFallback · helpers                                       — react
  layout/       ResizableThreeColumnLayout                                   — react-resizable-panels
```

**Dependency rule (inward only):** `theme` → nothing. `foundation` / `http` / `sse` / `hooks` → zero project deps. `primitives` / `feedback` / `chat` / `layout` → peer libs + `theme` tokens. **Nothing imports a consumer store / API / domain type / the host `@/` alias.** This is the domain-blindness invariant, enforced by a lint (§8).

Each subpath is independently importable — take only what you need.

---

## 4. The composition pattern (engine vs binding)

The kit ships **domain-blind engines**; the consumer keeps thin **binding** components/modules that inject app state + domain config. This is the core mental model — follow it when extending.

| Kit engine (domain-blind) | Consumer binding (GridIQ example) |
|---|---|
| `Toaster({ toasts, onDismiss, toneStrip? })` | wrapper reads `useToastStore`, passes `situation-*` tone palette |
| `CommandPaletteBase({ commands })` | builds the command list from stores |
| `TimedProgressBar/Panel({ startedAt, estimateMs, messages })` | reads scan timing from a store |
| `HelpOverlay({ open, onClose, shortcuts })` | passes the app's shortcut table |
| `useKeydownDispatcher(bindings)` | `useGlobalShortcuts` defines the bindings |
| `parseResponse(res, { onUnauthorized })` | `api/client.ts` injects the MSAL redirect + dev-identity headers |
| `@agentkit-ui/foundation` severity engine | `lib/severity.ts` adds the `situation-*` Tailwind class maps |
| `ResizableThreeColumnLayout({ left, center, right })` | `PanelLayout` supplies the column content |
| `parseSSEStream(body, onFrame)` | each `api/*.ts` keeps its own `fetch` + `switch(event)` |

**Rule:** if a feature needs app state, a store, an auth SDK, or domain labels, the kit takes them as **props / params / callbacks** — it never reaches out. The auth SDK (MSAL, etc.) is *never* hardcoded in the kit; it is injected (see `@agentkit-ui/http`).

---

## 5. API reference (per subpath)

### `@agentkit-ui/theme`
- `preset.cjs` — Tailwind preset: the generic colour groups (brand/neutral/text/border/status/overlay/header/section/teams/…), the `fontSize` scale, the `pulse-dot` keyframe, and the `@tailwindcss/typography` + `@tailwindcss/container-queries` plugins. Consume via `presets: [...]`.
- `tokens.css` — **default** values for every `--color-*` / `--font-*` var the preset references (neutral dark theme). Import once; override to re-theme.
- `animations.css` — keyframes + utility classes the components reference by name: `animate-fade-in`, `animate-spin-slow`, `animate-fresh-hairline`, `animate-highlight-pulse`, `fly-from-origin`, plus the `--motion-ease` token.
- `TOKENS.md` — the full token contract (which var feeds which Tailwind group).

### `@agentkit-ui/foundation` — severity vocabulary engine (zero deps)
- `type RawSeverity = "CRITICAL"|"MAJOR"|"SERIOUS"|"INVESTIGATE"|"minor"`
- `SEVERITIES_BY_RANK: readonly RawSeverity[]` — worst-first.
- `SEVERITY_RANK: Record<RawSeverity, number>` — derived rank map (lower = worse).
- `rankFor(raw: string): number` — rank with unknown → last slot.
- `type Bucket = "Critical"|"Major"|"Minor"|"Suspect"`, `BUCKETS`, `BUCKET_FROM_RAW`.
- `bucketFor(raw: string): Bucket` — operator-facing fold, unknown → `Suspect`.
- *No styling* — a consumer layers its own class maps on top.

### `@agentkit-ui/http` — auth-SDK-agnostic HTTP helpers (zero deps)
- `class ApiError extends Error { status: number; detail: string }`
- `extractErrorMessage(body: unknown, fallback: string): string` — handles `{detail:"…"}` and `{detail:{message:"…"}}`.
- `parseResponse<T>(res: Response, { onUnauthorized? }): Promise<T>` — status-check + JSON parse; fires `onUnauthorized` on 401, throws `ApiError` on non-2xx.
- `buildBearerHeaders(getToken: () => Promise<string|null|undefined>): Promise<Record<string,string>>` — `{ Authorization: "Bearer …" }` or `{}`.

### `@agentkit-ui/sse` — SSE wire parser (zero deps)
- `interface SSEFrame { event: string; data: string; parsed: Record<string, unknown> }`
- `parseSSEStream(body: ReadableStream<Uint8Array>, onFrame: (f: SSEFrame) => boolean|void, opts?: { onParseError? }): Promise<void>` — decode/CRLF-normalise/buffer/split-on-blank-line/parse `event:`+`data:`/JSON-decode. Return `true` from `onFrame` to stop early (terminal event). Owns the reader lifecycle. Consumer keeps `fetch` + auth + `switch(frame.event)`.

### `@agentkit-ui/hooks` — React hooks (react only)
- `useAutoScroll(...)` — smart scroll-to-bottom for chat/log timelines.
- `usePersistence(...)` — localStorage sync helper.
- `useTypewriter(...)` — character-by-character streaming text animation.
- `useKeydownDispatcher(bindings: KeyBinding[], target?: Document)` — document-level shortcut engine; editable-target guard; exact modifier matching; first match wins. `KeyBinding = { key, ctrlOrMeta?, alt?, shift?, allowInEditable?, handler(e) }`. Also exports `isEditableTarget(e)`.
- `useOutsideClick(ref, onOutside, active?)` — click-away handler; only listens while `active`.
- `useDebouncedValue<T>(value, { delayMs?=150, immediate?=false })` — debounce with an immediate flush escape hatch (built for streaming text).

### `@agentkit-ui/stores` — zustand stores (zustand peer)
- `useToastStore()` → `{ toasts, pushToast(input): number, dismissToast(id), clearToasts() }`; `ToastEntry = { id:number, title, body?, tone, durationMs, pulse? }`, `ToastTone = "info"|"success"|"warning"|"error"`, `ToastInput = Omit<ToastEntry,"id">`.
- `usePaletteStore()` → `{ open, helpOpen, openPalette, close, togglePalette, openHelp, closeHelp, toggleHelp }` (mutually exclusive).

### `@agentkit-ui/primitives` — presentational components
- `<MarkdownRenderer content={string} />` — react-markdown + GFM + syntax highlight + copy buttons.
- `<DateRangePicker … />` — popover calendar (react-day-picker v9), `"YYYY-MM-DD HH:MM"` wire format.
- `<ValueDial … />` — SVG rotary knob (keyboard + wheel).
- `<TeamsCallModal … />` — full-viewport mock call overlay (contact injected).
- `<StreamingIndicator />` — three-dot pulse (uses the `pulse-dot` keyframe).
- `normalizeBullets(text): string` — prose→markdown-list safety net.
- `<ErrorBoundary>{children}</ErrorBoundary>` — render-crash boundary + reload UI (token-styled).

### `@agentkit-ui/feedback` — overlays & notifications
- `<Toaster toasts onDismiss toneStrip? toneIconColor? pulseClassName? />` — fixed toast stack; generic `status-*` tone defaults, overridable.
- `<HelpOverlay open onClose shortcuts={ShortcutGroup[]} title? />` — injected-shortcut cheat-sheet modal (portal).
- `<CountdownPill seconds label? icon? unit? />` — self-ticking "retrying in N s" pill.
- `<CommandPaletteBase open onClose commands={Command[]} placeholder? emptyLabel? />` — ⌘K palette engine (substring scorer, keyboard nav, portal). `Command = { id, label, hint?, keywords?, group, run() }`.
- `<TimedProgressBar startedAt estimateMs />` + `<TimedProgressPanel startedAt estimateMs messages messageRotateMs? icon? footnote? />` — time-based progress for single-shot ops; exports `progressFraction(elapsedMs, estimateMs)` + `formatSeconds(ms)`.

### `@agentkit-ui/chat` — streaming-chat result scaffold
- `<ToolResultCard scope? signal? note? noteTone? error? >{body}</ToolResultCard>` — the 4-band layout (scope badges → signal chips → note banner → body), with a typed-error short-circuit. Sets `data-tool-card`. Types: `ScopeBadge`, `SignalChip`, `SignalTone`, `NoteTone`, `ToolResultCardProps`.
- `<ResultTable rows columns? previewRows? prominentColumns? />` — scrollable table primitive with preview cap + column hints.
- `<ArgumentsGrid … />` — generic JSON argument renderer.
- `<JsonFallback result={string} />` + `<ToolResultError detail={string} />` — JSON-by-design fallback + inline error banner.
- helpers: `severityColor(level)`, `parseToolResult<T>(s)`, `formatCell(v)`, `extractError(parsed)`.
- **The kit owns the scaffold, not the renderer registry.** The `TOOL_RENDERERS` / `TOOL_ARGS_RENDERERS` / `TOOL_PROMINENT_COLUMNS` mapping (tool-name → component) stays in the consumer.

### `@agentkit-ui/layout`
- `<ResizableThreeColumnLayout left center right sizes? minSizes? panelClassNames? separatorClassName? />` — drag-resizable 3-column shell (react-resizable-panels). Consumer supplies column content + headers.

---

## 6. Theming

Components reference only semantic Tailwind tokens (`text-text-secondary`, `bg-neutral-bg1`, `text-status-error`, …) that resolve to `var(--color-*)` / `var(--font-*)`. Three steps to theme (all in §1):

1. `presets: [require(".../theme/preset.cjs")]` + add the kit src to Tailwind `content`.
2. `@import "@agentkit/ui/theme/tokens.css"` for the default palette.
3. Redefine any `--color-*` / `--font-*` var in a stylesheet loaded **after** the default (e.g. a `:root` block, or a `[data-theme="light"]` selector) to re-skin.

The full var contract is in [src/theme/TOKENS.md](src/theme/TOKENS.md). **Domain colour groups** (a host app's situation/priority/etc.) are *not* part of the kit — define them in your own `tailwind.config.js` + tokens.

---

## 7. Extending the kit

> Read this before adding or changing anything. The kit's value is its discipline; an undisciplined addition erodes it for every consumer.

### Decision: does it belong in the kit?
Add to the kit **only if** the thing is domain-blind — no store/API/domain-type import, no hardcoded domain labels/colours. If it needs any of those, build it as a **consumer binding** (§4) and, if there's a reusable core, extract that core into the kit and inject the rest.

### Where it goes
| If it is… | Put it in |
|---|---|
| pure data/vocabulary + functions | `foundation/` |
| an HTTP/fetch helper | `http/` |
| an SSE/stream helper | `sse/` |
| a React hook | `hooks/` |
| a zustand store | `stores/` |
| a presentational component (no overlay) | `primitives/` |
| an overlay / toast / progress / palette | `feedback/` |
| chat-result rendering | `chat/` |
| a page/region layout shell | `layout/` |
| a colour/size/motion token | `theme/` (tokens.css + TOKENS.md, or preset.cjs for a Tailwind group) |

### Steps to add a component/hook
1. Create the file in the right subpath. Imports: peer deps + sibling kit modules only. **No `@/` host-alias import.**
2. Style with semantic tokens only — `text-xs`, `bg-neutral-bg1`, `text-status-error`. **No** `text-[14px]`, `bg-[#…]`, hex, or arbitrary px (the prose-`em` exception is `MarkdownRenderer`-only; `vw`/`vh` are allowed).
3. If it needs app state / domain config, take it as **props/params/callbacks**.
4. Export it from the subpath barrel (`src/<area>/index.ts`) with its public types.
5. The root barrel (`src/index.ts`) re-exports each subpath. **If two subpaths export the same name** (e.g. `ToastTone` in both `stores` and `feedback`), the root barrel must re-export one explicitly to avoid a TS2308 collision — see the existing `stores` handling in `src/index.ts`.
6. If you add a token, add it to **both** `theme/tokens.css` (a default value) and `theme/TOKENS.md` (the contract row). If it's a Tailwind colour group, add it to `theme/preset.cjs`.
7. If you add a new subpath, add it to `package.json` `exports` + the root barrel + the README API table.
8. Add a unit test for any pure logic (see `tests/agentkit-ui/` + `tests/sse/`). Bug fix → regression test.
9. Run the regression loop (§8). Do not weaken a contract-pin test to make it pass.

### Modifying an existing component
- Preserve the public prop/return shape unless you intend a breaking change (the kit has **no backwards-compat shims** by policy — fix all call sites in the same change).
- Keep `data-*` test hooks (`data-tool-card`, `data-testid="toaster"`, …) — consumer e2e suites assert them.
- Re-run the regression loop; the failing-test baseline must not grow.

---

## 8. Discipline & verification

Enforced by [.github/protocols/regression_loop_frontend.md](../../../../.github/protocols/regression_loop_frontend.md). Run it after any change. Gates, in order:

1. **Typecheck** — `tsc --noEmit` clean (resolves the aliases; catches stale imports first).
2. **Unit tests** — `vitest run`; the failing-file set must not grow beyond the pre-existing baseline, and the contract pins stay green (`tests/chat/toolResultCard.test.tsx`, `tests/chat/toolRenderers.test.tsx`, `tests/sse/parseSSEStream.test.ts`, `tests/agentkit-ui/foundation.test.ts`).
3. **Build** — `vite build` (Rollup resolves the alias differently than tsc; both must pass).
4. **Token-discipline lint** — zero arbitrary `text-[…]` / `bg-[#…]` / hex / arbitrary-px in package source (prose-`em` + `vw`/`vh` allowlisted).
5. **Domain-blindness lint** — zero imports of a host `@/stores|api|config|features` path or MSAL/azure SDK.

One-liner lints (from `app/frontend/`):
```bash
# domain-blindness + host-alias leak
grep -rnE "from ['\"]@/" packages/agentkit-ui/src                                   # → 0
# arbitrary tailwind (excluding the prose/vw allowlist)
grep -rnE 'text-\[[0-9]|bg-\[#|\[#[0-9a-fA-F]{3,}|w-\[[0-9]+px\]' packages/agentkit-ui/src \
  | grep -vE 'text-\[inherit\]|text-\[0\.[0-9]+em\]|max-w-\[[0-9]+vw\]|max-h-\[[0-9]+vh\]'
```

---

## 9. Gotchas / FAQ

- **Classes missing in production?** The kit src isn't in your Tailwind `content` → its utilities got purged. Add `./packages/agentkit-ui/src/**/*.{ts,tsx}`.
- **`@` alias swallowing `@agentkit-ui/…`?** Declare the more-specific `@agentkit-ui` alias **before** `@` in `vite.config.ts`.
- **Animations not playing?** You imported `tokens.css` but not `animations.css`. Both are required.
- **TS2308 "already exported"** at the root barrel → two subpaths export the same symbol; re-export one explicitly in `src/index.ts`.
- **`npx vitest` hangs trying to network-install?** `node_modules` was wiped — run `npm install`, then use `./node_modules/.bin/vitest`.
- **`react-resizable-panels` version errors** (e.g. `Group` rejecting a prop) — the kit targets `>=4`; props differ across majors. Pin the peer to match.
- **Where do domain colours go?** Never in the kit. The consumer's `tailwind.config.js` + tokens own `priority`/`severity`/etc.

---

## 10. Roadmap

**Shipped:** primitives, chat scaffold, hooks, feedback overlays, SSE parser, foundation severity engine, stores, http helpers, layout shell, full theme (preset + default tokens + animations).

**Inc-5 backlog** (deferred — component-shell extractions on live-critical surfaces that need careful API design; a hasty lift risks regressing the chat stream / centre-nav / tab bar): `ToolCallCard` shell + `useElapsedTimer`, `TabBar<T>` + `useConfirmAction`, `ModeChipRow<T>` (portal-positioning concern), `Dropdown<T>` shell, `ChatShell`, `MessageBubble` shell. Plus a standalone zero-domain-import examples app. See [genericize/TIER2_FRONTEND_EXTRACTION_PLAN.md](../../../../genericize/TIER2_FRONTEND_EXTRACTION_PLAN.md).
