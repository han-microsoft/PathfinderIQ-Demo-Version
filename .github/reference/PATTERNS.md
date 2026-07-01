# PATTERNS — what good looks like

Eight patterns, language-agnostic, each proven across two independent production
agentkits. Principle + why + the seed tenet it serves. Code exemplars in
[python/](python/). Read once; internalize the shape.

Register: smart caveman. Each pattern = `[shape] [why]. [rule].`

---

## 1. Error-envelope chokepoint

**Shape.** Every fallible boundary returns errors through ONE function, not
open-coded at each site. The function caps detail length, strips URLs/secrets,
classifies into a machine-readable code.

**Why.** 20+ scattered `return {"error": str(exc)}` sites drift: some leak stack
traces, some leak internal hostnames, some leak nothing. A chokepoint makes the
sanitization contract un-bypassable and a shape change a one-line edit.

**Rule.** No raw exception text crosses a boundary. Cap, strip, classify — in one
home (C1). Surface errors loud + structured, never silent (T4).

Exemplar: [python/error_envelope.py](python/error_envelope.py).

---

## 2. Resilience as a pure state machine

**Shape.** Circuit breaker owns ONLY the Closed→Open→Half-Open transitions.
Retry, fallback, concurrency are the caller's concern. Thread-safe via a plain
lock (no await inside), so it works from sync and async callers alike.

**Why.** Mixing breaker + retry + fallback in one class makes each untestable and
the whole un-reusable. A pure state machine is a leaf: drop it in anywhere, it
degrades cleanly when the dependency dies.

**Rule.** One concern per primitive (P1). The breaker fails fast and loud; the
caller decides what to return when it's open. Removal breaks nothing (P2).

Exemplar: [python/circuit_breaker.py](python/circuit_breaker.py).

---

## 3. Resolve-once request scope (contextvar)

**Shape.** Build a frozen per-request snapshot once at entry, bind it to a
contextvar, read it anywhere downstream — never re-read config deep in the stack.
Opaque bags hold domain config so the carrier never names a domain.

**Why.** Re-reading settings deep in the call tree couples every layer to config
and breaks under concurrency/test. A frozen contextvar snapshot is thread-safe,
async-safe, test-isolated, and domain-blind.

**Rule.** Resolve once, freeze, distribute. The carrier knows request identity;
domain specifics go in opaque bags it never inspects (P1, P2).

Exemplar: [python/request_scope.py](python/request_scope.py).

---

## 4. Duck-typed foreign-object adaptation

**Shape.** Read external SDK objects via `getattr(obj, "field", default)` instead
of importing the SDK type. Bind the SDK at exactly one seam module; everything
else stays import-free of it.

**Why.** Importing an SDK type everywhere couples the whole codebase to one
vendor + version. Duck-typing at the boundary lets the core boot without the SDK
installed and lets you swap vendors by editing one seam.

**Rule.** Core imports no vendor SDK. Adapt by attribute-read at the boundary;
isolate the hard import in a single named seam (P2).

Exemplar: [python/duck_typed_adapter.py](python/duck_typed_adapter.py).

---

## 5. Inward-only dependency DAG

**Shape.** Rings, innermost-out. Inner ring = contracts/models (stdlib + one
validation lib). Each outer layer imports ONLY from rings to its left. Capstone
app at the edge. No cycles, ever.

**Why.** A cyclic or tangled import graph makes any module impossible to test or
remove in isolation. A strict inward DAG means every layer is independently
buildable and the blast radius of a change is bounded.

**Rule.** Dependencies point inward only. The seed's `cycle_scan` /
`graph query cycles` enforce this mechanically — a new cycle is stop-the-line.

---

## 6. Lazy imports behind extras

**Shape.** Base install = a handful of light deps. Heavy SDKs (cloud, ML,
transport) import lazily at the call seam, gated behind named `[extras]`. Absent
SDK → the feature degrades to noop/None, never an import crash.

**Why.** Forcing every consumer to install every backend bloats the wheel and
couples unrelated features. Lazy + extras keeps the base bootable everywhere and
lets a consumer pay only for what it uses.

**Rule.** Importing a package must not import its heavy optional deps. Degrade
cleanly when an optional dep is absent (P2); declare the extra explicitly.

---

## 7. Injection seams over hard wiring

**Shape.** A reusable module declares what the consumer must supply — a Protocol,
a callable, a factory — and wires it in. It never imports the consumer. Default
provided for the zero-config path; production swaps the implementation.

**Why.** A module that hard-imports its consumer can't be reused or tested in
isolation. A declared seam inverts the dependency: the consumer plugs in, the
module stays generic.

**Rule.** Reusable code depends on abstractions it declares, never on the
concrete consumer (P1, dependency inversion). Ship a working default; document
the seam.

---

## 8. Streaming as an enforced event contract

**Shape.** A streaming response is a sequence of typed frames with a *guaranteed
order* and *exactly one terminal*. Define the vocabulary + order once; verify it
with an executable probe, not by eyeballing. Aggregate partial fragments (e.g.
tool-call args arriving across chunks) into coherent start/delta*/end lifecycles.
Bound every wait (stall timeout); race a cancel (abort); always emit one terminal.

**Why.** Naive `async for chunk: yield chunk` drops fragments, mis-orders parallel
tool calls, hangs on a stalled model, and ends ambiguously. Clients and proxies
then break in ways impossible to debug after the fact. An enforced contract makes
the stream's correctness a checked fact (P7), not a hope.

**Rule.** The order is a contract; a probe asserts it (exactly one terminal,
nothing after it, metadata before done, every end has a start). Bound every
wait; surface failures as a terminal ERROR frame, never a hang (T4).

Exemplar: [python/sse_stream/](python/sse_stream/) — multi-module spine with a
self-proving demo (happy path, stall, abort).

---

## The through-line

All seven serve the two laws: maximize true-state-per-token (a chokepoint,
a frozen scope, a strict DAG are *legible* — you can reason about them locally)
and minimize decay (one home, leaf modules, no cycles, no hidden coupling resist
rot). Good code is code the next agent can understand in isolation and remove
without fear.
