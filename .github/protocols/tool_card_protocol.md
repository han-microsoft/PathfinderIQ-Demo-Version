# Tool-card Protocol — authoring a tool card

Bespoke chat cards for **ordinary tool results**, keyed off the tool `name` /
family (storage.\*, search.\*, cosmos.\*, …) rather than the DAA `card_kind`
discriminator the [renderer_protocol.md](./renderer_protocol.md) compiler cards
use. Sibling layer, identical discipline: central registry, one-file-per-card,
**a schema-driven generic floor that never shows raw JSON**. Scope: `vm_agent/`.

## When this vs the compiler-card protocol

| Result | Discriminator | Layer | Protocol |
|---|---|---|---|
| DAA compiler flow (`workflows.run`, `assets.*`, `sources.discover`, `access.*`) advertising top-level `card_kind` | `card_kind` | compiler card (`cards/`) | [renderer_protocol.md](./renderer_protocol.md) |
| Any other registered tool (storage / search / cosmos / fabric / catalogue / sources / profiles / …) | tool **name** prefix | tool card (`toolcards/`) | **this file** |

`CompilerCard.tsx` resolves the compiler `card_kind` registry **first**, so a
DAA result is never shadowed by the tool-name layer. Everything else resolves
in the tool-card registry: a bespoke family card if one matches the tool name,
else the **schema-driven generic card** (the floor). Only a **non-JSON** tool
result (e.g. a shell exec dump) resolves to null → the generic `ToolCallDisplay`.

## Architecture (read once)

- Chat tool calls arrive as `ToolCall { name, arguments, result }`. `result` is
  an opaque STRING (the tool payload JSON, JSON-encoded by the MAF bridge —
  `vmagent/runtime/maf/bridge.py::_result_to_str`).
- The tool's `ToolDefinition.output_schema` is the *contract* a card renders.
  In practice `output_schema` is often empty in the registry, so the generic
  floor renders the **actual parsed payload structure** (fields + tables) — the
  schema is the intent; the payload is the data.
- Central registry: [ui/src/components/chat/toolcards/toolRegistry.ts](../../ui/src/components/chat/toolcards/toolRegistry.ts).
  Lookup ONLY — never a switch on a tool name.
- Dispatch: [ui/src/components/chat/cards/CompilerCard.tsx](../../ui/src/components/chat/cards/CompilerCard.tsx)
  → `resolveCard` (compiler) → `resolveToolCard` (this layer) → `ToolCallDisplay`.
- Self-registration: each `toolcards/<Family>Card.tsx` calls
  `registerToolCard(...)` at module scope;
  [toolcards/index.ts](../../ui/src/components/chat/toolcards/index.ts) imports
  each file for that side effect. **Add a card = one new file + one import line.
  The core (`toolRegistry.ts`) is never touched.**
- The schema-driven floor
  ([toolcards/GenericToolCard.tsx](../../ui/src/components/chat/toolcards/GenericToolCard.tsx))
  registers at the lowest priority and matches every tool, so `resolveToolCard`
  always returns a renderable card for a JSON-object payload. **The floor never
  shows raw JSON** — it renders `SchemaBody` (labelled fields + bounded tables).
- Shared widgets: [toolcards/widgets.tsx](../../ui/src/components/chat/toolcards/widgets.tsx)
  (`MiniTable`, `StatTiles`, `SchemaBody`, `firstObjectArray`, `toneFromPayload`,
  `humanise`). Draw the structured render from these; do not hand-roll tables.

## Steps

1. **Contract.** Read the tool's `ToolDefinition` (and handler) in
   `vmagent/tools/registry_defs/<family>.py` to learn the payload shape the card
   renders (the principal collection key, the scalar fields, the `status`). The
   `output_schema` is the contract; capture the live payload shape if empty.
2. **Create `toolcards/<Family>Card.tsx`.** Implement a `ToolCardModule`:
   - `key`: the family name (e.g. `"storage"`).
   - `match(toolName, payload, toolCall)`: a name/prefix test, e.g.
     `toolName.startsWith("storage.")`.
   - `component`: a pure, read-only `CardProps` renderer. Use `CardShell`
     **with `variant="tool"`** (tags `data-toolcard`, not `data-compiler-card`)
     + the shared widgets. Find the principal collection with `firstObjectArray`
     and render `MiniTable`; show salient scalars with `StatTiles`/`Field`; fall
     back to `SchemaBody` for anything unmodelled. Never dump raw JSON.
   - Call `registerToolCard({...})` at module scope.
3. **Register — one line.** Add `import "./<Family>Card";` to
   [toolcards/index.ts](../../ui/src/components/chat/toolcards/index.ts) **above**
   the `import "./GenericToolCard";` floor line.
4. **Fallback (don't break it).** Unmatched tool → the schema-driven generic
   card → never raw JSON. Do not register a family card that matches `() => true`
   — that is the floor's job.
5. **Test** ([ui/tests/toolCardRegistry.test.tsx](../../ui/tests/toolCardRegistry.test.tsx)):
   - add a representative payload fixture; assert `resolveToolCard` resolves the
     tool name to YOUR family key (not `generic`);
   - keep the unknown-tool assertion green (`custom.brand_new` → `generic`, not
     null, not raw JSON);
   - keep the no-shadow assertion green (a `card_kind` result → compiler card,
     `data-toolcard` absent).
6. **Verify.** `cd ui && npx tsc --noEmit && npx vitest run && npm run build`
   (Monaco stays lazy); ui e2e
   ([ui/e2e/02-tool-call.spec.ts](../../ui/e2e/02-tool-call.spec.ts) — deterministic
   SSE interception: a bespoke card renders, the generic floor renders labelled
   fields not raw JSON, a `card_kind` result still resolves the compiler card, a
   non-JSON result falls to `ToolCallDisplay`). `CHAT_CONTRACT_PROBE_OK` must be
   unaffected (the `card_kind` wire is byte-pinned). Emit `TOOL_CARD_PROBE_OK`
   (the registry-resolution suite green).

## Card template (copy-paste)

```tsx
/**
 * <Family>Card — <family> tool results.
 * Shapes: <tool>.<verb> → { <collection>:[{...}], count, status }
 */
import { Sparkles } from "lucide-react";
import { CardShell } from "../cards/CardShell";
import { asString } from "../cards/parse";
import { registerToolCard } from "./toolRegistry";
import { MiniTable, SchemaBody, StatTiles, firstObjectArray, humanise, toneFromPayload } from "./widgets";
import type { CardProps } from "./types";

function MyFamilyCard({ payload, toolCall }: CardProps) {
  const status = asString(payload["status"]);
  const collection = firstObjectArray(payload, ["items"]); // your principal key
  const count = typeof payload["count"] === "number" ? (payload["count"] as number) : collection?.rows.length;
  return (
    <CardShell
      variant="tool"
      cardKind="myfamily"
      icon={Sparkles}
      title={toolCall.name || "myfamily"}
      statusLabel={status || undefined}
      tone={toneFromPayload(payload)}
      summary={count != null ? `${count}` : undefined}
      defaultExpanded
    >
      <StatTiles stats={[{ label: collection ? humanise(collection.key) : "Count", value: count ?? undefined }]} />
      {collection ? <MiniTable rows={collection.rows} /> : <SchemaBody payload={payload} skip={["status", "count"]} />}
    </CardShell>
  );
}

registerToolCard({
  key: "myfamily",
  match: (name) => name.startsWith("myfamily."),
  component: MyFamilyCard,
});
```

Then add `import "./MyFamilyCard";` to `toolcards/index.ts` (above the generic
floor import). One file + one line; the core is untouched.

## Hard rules

- The generic floor MUST render structured fields/tables — NEVER a raw JSON dump.
- Family cards use `CardShell variant="tool"` (`data-toolcard`); only compiler
  cards use `data-compiler-card`. Do not cross the selectors (the e2e regression
  guard depends on it).
- Never register a tool card matching `() => true` — that is the generic floor.
- Do not duplicate a DAA compiler card: `assets.*` / `workflows.run` /
  `sources.discover` / `access.*` advertise `card_kind` and resolve in the
  compiler layer first. Build tool cards only for families WITHOUT a `card_kind`.
- One file per card. The core (`toolRegistry.ts`) is never edited to add a card.
