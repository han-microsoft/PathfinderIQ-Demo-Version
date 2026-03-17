# Localization (i18n) — Developer Guide

> **Read this before adding any user-facing text to the frontend or
> modifying agent prompt behavior.**

---

## Architecture overview

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND                                                │
│                                                          │
│  src/locales/                                            │
│    ├── en.json         ← English (canonical, all keys)   │
│    ├── ja.json         ← Japanese                        │
│    ├── index.ts        ← translate() + fallback chain    │
│    └── README.md       ← THIS FILE                       │
│                                                          │
│  src/stores/localeStore.ts   ← Zustand: locale state     │
│  src/hooks/useTranslation.ts ← React hook: t() function  │
│  src/api/client.ts           ← X-User-Language header    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  BACKEND                                                 │
│                                                          │
│  app/_middleware.py           ← reads X-User-Language     │
│  app/foundation/request_context.py ← language field      │
│  agents/_prompts.py          ← appends language block     │
│  app/services/llm/agent.py   ← cache key includes lang   │
└──────────────────────────────────────────────────────────┘
```

---

## Fallback chain (graceful degradation)

The system is designed so that **missing translations never cause errors**.
Every layer has an explicit English fallback:

```
Active locale JSON  →  en.json  →  raw key string
     (ja.json)         (always)     ("chat.foo")
```

| Scenario | What happens |
|----------|-------------|
| Key exists in active locale (e.g. `ja.json`) | Japanese string shown |
| Key missing from `ja.json` but exists in `en.json` | English string shown |
| Key missing from ALL locale files | Raw key shown (e.g. `"chat.foo"`) — visual bug cue for developer |
| `localStorage` has invalid locale code | Falls back to `"en"` |
| `X-User-Language` header has unrecognized value | Backend falls back to `"en"` (allowlisted) |
| Agent cache built under different language | Cache key includes language → agent rebuilt automatically |
| `translate()` called outside React (stores, utils) | Works — `translate(locale, key)` is a pure function |

---

## How to add a new translatable string

### Step 1: Add the key to `en.json`

```json
"myFeature.buttonLabel": "Click me"
```

**Key naming convention**: `{component}.{element}` using camelCase.
Examples: `chat.placeholder`, `sidebar.conversations`, `agent.name.orchestrator`.

### Step 2: Add the translation to other locale files

```json
// ja.json
"myFeature.buttonLabel": "クリック"
```

If you don't have a translation yet, **skip this step**. The fallback
chain will show the English text until a translation is added.

### Step 3: Use `t()` in your component

```tsx
import { useTranslation } from "@/hooks/useTranslation";

function MyComponent() {
  const { t } = useTranslation();
  return <button>{t("myFeature.buttonLabel")}</button>;
}
```

That's it. The component will:
- Show the active locale's text
- Fall back to English if the key is missing
- Re-render automatically when the user switches languages

### Interpolation

For dynamic values, use `{placeholder}` syntax:

```json
// en.json
"replay.stepOf": "Step {current} of {total}"

// ja.json
"replay.stepOf": "ステップ {current} / {total}"
```

```tsx
t("replay.stepOf", { current: 3, total: 10 })
// → "Step 3 of 10" (en) or "ステップ 3 / 10" (ja)
```

---

## How to use `t()` outside React components

For non-component code (helper functions, utility modules), pass `t` as
a parameter instead of calling the hook:

```tsx
// Helper function — receives t as parameter
function getCapabilities(tools: string[], t: (key: string) => string): string[] {
  return tools.map(tool => t(`tool.name.${tool}`) || toTitleCase(tool));
}

// Component — passes t to the helper
function AgentCard() {
  const { t } = useTranslation();
  const caps = getCapabilities(agent.tools, t);
}
```

**Rule**: Only call `useTranslation()` inside React function components
or custom hooks. Everywhere else, thread `t` as a parameter.

---

## How to add scenario-specific content translations

Agent names, descriptions, product summaries, and tool names use a
**locale-first, source-fallback** pattern. The locale key is checked
first; if missing, the value from `scenario.yaml` or the hardcoded
fallback is used.

| Content | Locale key pattern | Fallback |
|---------|-------------------|----------|
| Agent display name | `agent.name.{agentId}` | `agent.name` from scenario.yaml |
| Agent description | `agent.desc.{agentId}` | `agent.description` from scenario.yaml |
| Agent product summary | `agent.product.{agentId}` | Hardcoded English in AgentTabBar |
| Tool display name | `tool.name.{functionName}` | `toTitleCase(functionName)` |
| Capability label | `agent.capability.{namespace}` | `toTitleCase(namespace)` |

The check pattern in code:
```tsx
const localeKey = `agent.name.${agent.id}`;
const localeVal = t(localeKey);
// If t() returned the raw key, it means no translation exists → use source
const displayName = localeVal !== localeKey ? localeVal : agent.name;
```

---

## How to add a new language

1. **Create the locale JSON file**: `src/locales/{code}.json`
   - Copy `en.json` as a starting point
   - Translate all values (keys stay the same)
   - Missing keys are fine — English fallback kicks in

2. **Register in `localeStore.ts`**:
   ```ts
   export type LocaleCode = "en" | "ja" | "ko";  // add new code

   export const SUPPORTED_LOCALES: LocaleInfo[] = [
     { code: "en", label: "English", englishName: "English" },
     { code: "ja", label: "日本語",  englishName: "Japanese" },
     { code: "ko", label: "한국어",  englishName: "Korean" },  // add
   ];
   ```

3. **Import in `locales/index.ts`**:
   ```ts
   import ko from "./ko.json";

   const MESSAGES: Record<string, Record<string, string>> = {
     en, ja, ko,  // add
   };
   ```

4. **Register in backend middleware** (`app/_middleware.py`):
   ```python
   _ALLOWED_LANGS = frozenset({"en", "ja", "ko"})  # add
   ```

5. **Add language name mapping** in `agents/_prompts.py`:
   ```python
   _LANG_NAMES = {
       "ja": "Japanese", "ko": "Korean",  # add
   }
   ```

That's it. The dropdown auto-populates from `SUPPORTED_LOCALES`.

---

## Backend: How agent language works

When the user selects a non-English language:

1. Frontend sends `X-User-Language: ja` header on every API request
2. Middleware reads it, validates against allowlist, stores in `RequestContext.language`
3. `agents/_prompts.py` appends this to **every agent's** system prompt:
   ```
   ## Response Language

   You MUST respond entirely in Japanese. All text output — analysis,
   summaries, explanations, recommendations, and natural language —
   must be in Japanese. Technical identifiers (node IDs, query syntax,
   tool names, JSON keys) remain in their original form. Do not mix
   languages.
   ```
4. Agent cache key is `(agent_id, model, language)` — switching language
   rebuilds agents with the updated system prompt

This means **all agents** (orchestrator + all specialists) respond in the
selected language. Tool calls remain in English (function names, arguments,
JSON keys are technical identifiers).

---

## Rules for future features

1. **Never hardcode user-facing English in JSX**. Always use `t("key")`.
2. **Add the key to `en.json` first**. Other locales are optional (fallback works).
3. **Use `useTranslation()` hook** in React components. Pass `t` as parameter to helpers.
4. **Aria labels and titles count** — screen reader text must be translated too.
5. **Error messages shown to users** must use `t()`. Console logs stay English.
6. **Don't translate**: CSS class names, event names, API paths, console.log, technical identifiers.
7. **Test with a non-English locale** to catch hardcoded strings visually.

---

## Key namespace conventions

| Prefix | Used for |
|--------|----------|
| `app.*` | App-wide (brand name) |
| `auth.*` | Login/authentication |
| `chat.*` | Chat input, messages, streaming |
| `chat.settings.*` | Context settings dialog |
| `chat.error.*` | Chat error messages |
| `tool.*` | Tool call display, status |
| `tool.name.*` | Tool display names |
| `agent.*` | Agent info cards, capabilities |
| `agent.name.*` | Agent display names |
| `agent.desc.*` | Agent descriptions |
| `agent.product.*` | Agent product summaries |
| `agent.capability.*` | Capability labels |
| `sidebar.*` | Sidebar sections, buttons |
| `sidebar.bugReport.*` | Bug report form |
| `sidebar.status.*` | Conversation status labels |
| `health.*` | Service health panel |
| `metrics.*` | Session metrics labels |
| `context.*` | Context inspector |
| `common.*` | Shared (Close, Cancel, Confirm, Loading) |
| `error.*` | Global error boundaries |
| `rateLimit.*` | Rate limit overlay |
| `scenario.*` | Scenario overlay |
| `obs.*` | Observability panel |
| `devNotes.*` | Developer notes overlay |
| `welcome.*` | Welcome screen |
| `replay.*` | Replay/demo tour |
| `graph.*` | Graph visualizer |
