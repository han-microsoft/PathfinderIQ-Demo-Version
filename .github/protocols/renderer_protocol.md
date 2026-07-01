# Renderer Protocol — authoring a compiler card

Bespoke chat cards for DAA compiler-flow tool results. Central registry,
one-file-per-card, generic fallback never breaks. This protocol is the exact
step list to add a card. Scope: `vm_agent/` only.

## Architecture (read once)

- Chat tool calls arrive as `ToolCall { name, arguments, result }`. `result` is
  an opaque STRING (the tool payload JSON).
- A DAA tool result advertises a STABLE top-level `card_kind` string. THAT is
  the discriminator. Contract: **a DAA result advertises `card_kind=X` → card X
  renders it.** A dedicated key (not `kind`) avoids collision with domain
  `kind` fields (e.g. `AssetContract.kind`).
- Central registry: [ui/src/components/chat/cards/registry.ts](../../ui/src/components/chat/cards/registry.ts).
  The core does registry lookup ONLY — never a switch on `card_kind`.
- Dispatch: [ui/src/components/chat/cards/CompilerCard.tsx](../../ui/src/components/chat/cards/CompilerCard.tsx)
  resolves a card off `card_kind`; on a miss (unknown kind, non-JSON result, or
  a throwing card) it falls through to the generic
  [ui/src/components/chat/ToolCallDisplay.tsx](../../ui/src/components/chat/ToolCallDisplay.tsx).
- Self-registration pattern: each `cards/<Name>Card.tsx` calls `registerCard(...)`
  at module scope; [ui/src/components/chat/cards/index.ts](../../ui/src/components/chat/cards/index.ts)
  imports each file for that side effect. **Adding a card = one new file + one
  import line. The core (`registry.ts`, `CompilerCard.tsx`) is never touched.**
- Eager imports (cards are light, dependency-free). Lazy-import only a single
  card if it ever pulls a heavy dependency.

## Steps

1. **Backend — advertise the kind.** In the DAA→tool boundary that produces the
   result the agent returns (`vmagent/daa/*` result builder OR the
   `vmagent/tools/registry_defs/<family>.py` handler), set a stable top-level
   `card_kind` on the payload dict. Keep it minimal and typed. Tag nested
   sub-payloads (e.g. `proof`, `materialized`) with their own `card_kind` if a
   parent card composes them.
2. **Frontend — create `cards/<Name>Card.tsx`.** Implement a `CardModule`:
   - `key`: the `card_kind` string.
   - `match(payload, toolCall)`: usually `payload["card_kind"] === "<kind>"`.
   - `component`: a pure, read-only `CardProps` renderer. No network calls — it
     renders only `payload` (already in the stream event). Use `CardShell` +
     `Field`/`Section` for consistent chrome. Degrade gracefully on absent
     fields (use the `asString`/`asArray`/`asRecord`/`asNumber`/`asBool`
     readers in [cards/parse.ts](../../ui/src/components/chat/cards/parse.ts)).
   - Call `registerCard({...})` at module scope.
3. **Register — one line.** Add `import "./<Name>Card";` to
   [cards/index.ts](../../ui/src/components/chat/cards/index.ts).
4. **Types.** Add the new `card_kind` to the `CardKind` union in
   [cards/types.ts](../../ui/src/components/chat/cards/types.ts). Extend
   `CardPayload` typing only if a card needs a shared shape.
5. **Test.**
   - ui unit ([ui/tests/cardRegistry.test.tsx](../../ui/tests/cardRegistry.test.tsx)):
     add a fixture; assert `resolveCard` resolves the new key to its component,
     and (still) that an UNKNOWN kind resolves to `null` (generic fallback).
   - backend pytest: if you added a `card_kind` at a DAA result, assert the
     result carries it (so the frontend contract can't drift) — see
     [tests/test_compiler_card_contract.py](../../tests/test_compiler_card_contract.py).
6. **Verify.** `cd ui && npx tsc --noEmit && npx vitest run && npm run build`;
   `PYTHONPATH=vm_agent pytest -q vm_agent/tests`; ui e2e incl the unknown-kind
   fallback guard ([ui/e2e/02-tool-call.spec.ts](../../ui/e2e/02-tool-call.spec.ts)).
   Confirm the generic fallback still handles unknown kinds.

## Card template (copy-paste)

```tsx
/**
 * <Name>Card — <one-line purpose>.
 * Backing DAA result: <module + fields>.
 */
import { Sparkles } from "lucide-react";
import { CardShell, Field } from "./CardShell";
import { registerCard } from "./registry";
import { asString } from "./parse";
import type { CardProps } from "./types";

function MyCard({ payload }: CardProps) {
  return (
    <CardShell cardKind="my_kind" icon={Sparkles} title="My card" tone="info">
      <Field label="Id" value={asString(payload["id"]) || undefined} />
    </CardShell>
  );
}

registerCard({
  key: "my_kind",
  match: (payload) => payload["card_kind"] === "my_kind",
  component: MyCard,
});
```

Then add `import "./MyCard";` to `cards/index.ts` and `"my_kind"` to `CardKind`.

## Hard rules

- NO giant switch in the core. The core does registry lookup only. Adding card
  N+1 must not grow `registry.ts` or `CompilerCard.tsx`.
- The generic `ToolCallDisplay` fallback MUST always handle an unknown/malformed
  kind. Never remove the fallback path.
- Cards are pure/presentational and read-only. No network calls, no store
  writes, no side effects beyond `registerCard` at import.
- Discriminator is `card_kind` (NOT `kind`) to avoid domain-field collisions.
- No CSP/auth weakening. Synthetic-only data in any live probe.
