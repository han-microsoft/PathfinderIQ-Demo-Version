# Engineering Philosophy

Doctrine layer. PART 0 of [copilot-instructions.md](copilot-instructions.md) holds
the axioms (2 laws, 10 tenets). This holds the *doctrine* PART 0 compresses out:
the reasoning, the **falsifiable test** per principle, the **conflict rule** when
two collide. Constitution links here. Read once to internalize the spirit, so you
rule correctly on cases the law did not enumerate.

No principle is belief. Each earns its place by producing measurable success. A
principle that stops paying = culled. This doc is held to its own Principle 7.

Each principle: **claim -> law it serves -> test that falsifies it -> rule when it conflicts.**

---

## P1 — One home per fact. Strict hierarchy. Forward-flowing imports.

No duplicated logic, module, or function. Used more than once -> flows from one
source. Packages form a DAG: imports point one direction, never cycle.

- **Serves:** Law 2 (dup = two truths drifting), C1.
- **Test (falsifiable):** grep finds the same logic in two homes -> FAIL. Import
  graph has a cycle -> FAIL. A change to one copy that needs the same change in
  another copy -> they were one fact, wrongly split -> FAIL.
- **Conflict (vs P2 decoupling):** share what is *one fact*; duplicate what is
  merely *similar shape*. Test: would a change to one necessarily force the same
  change to the other? Yes -> shared source (P1 wins). No -> coincidental
  similarity, keep apart (P2 wins). Premature shared-helper extraction breeds a
  `utils` god-module that couples the whole tree — that is P1 misapplied.

## P2 — Modular. Decoupled. Graceful at the seams.

No cross-cutting. No tangled imports. Every component is either an **optional
leaf** (remove it -> its feature degrades cleanly: informative error, logged,
documented; nothing unrelated breaks) or a **declared core dependency** (remove
it -> fail loud and fast at startup, never silent mid-request).

- **Serves:** Law 1 (a decoupled module is legible alone), T4.
- **Test (falsifiable):** remove a leaf component -> app still deploys, the rest
  still runs, the gap fails gracefully with a named error -> PASS. Removal causes
  silent/partial/mysterious breakage in an unrelated path -> FAIL (that is the
  cross-cutting tangle). A core dependency removed that fails *silently* instead
  of fast -> FAIL.
- **Conflict (vs P1):** see P1. **Forbidden third case:** a component whose
  removal breaks unrelated things in non-obvious ways. Hunt and kill it.

## P3 — Maximum legibility. No prose.

Max signal-per-token in code and docs. Register per
[copilot-communications-style.md](copilot-communications-style.md). Naming exact.
Structure self-evident.

- **Serves:** Law 1.
- **Test (falsifiable):** a section with articles/hedging/filler -> FAIL. A name
  that lies about what it holds -> FAIL. An agent must grep 40 files to learn what
  two docs should have told it -> the docs FAIL.
- **Conflict (vs completeness):** terse but true beats complete but unread. When
  cutting words drops a load-bearing fact, keep the fact, cut around it. Never cut
  the fact to hit a length.

## P4 — Determinism + traceability. Nothing without a reason.

Every behaviour explainable. Every branch a named cause. No magic constant, no
nondeterminism you cannot account for. Simplified structure, clear logic chains.

- **Serves:** T4 (visibility), T5 (mapped), Law 1.
- **Test (falsifiable):** a value/branch no one can explain the origin of -> FAIL.
  A flake that passes/fails nondeterministically -> FAIL (a race or hidden state).
  Two runs, same input, different output, unexplained -> FAIL.
- **Conflict (vs speed):** a fast path whose behaviour you cannot explain is not
  faster, it is unproven. Explain it or do not ship it.

## P5 — Nothing sacred. Restructure when principles demand it.

A change needing deep restructure to obey these principles -> do the restructure.
A codebase made more legible/solid/extensible by teardown -> tear it down. Run
[protocols/remodel_protocol.md](protocols/remodel_protocol.md).

- **Serves:** T10, C4, Law 2.
- **Test (falsifiable):** a god module survives because teardown felt risky, while
  a green core-flow gate existed -> FAIL (timidity, not discipline). A teardown
  shipped with no metric improved -> FAIL (churn, not strength).
- **Conflict (vs P-minimal / "minimal change"):** minimal is the default *within*
  a sound structure. When the structure itself violates P1/P2/P4, minimal patching
  *preserves* the violation — restructure wins. Test: does the small change lower
  illegibility or merely hide it? Hide -> restructure.

## P6 — Minimal change within a sound structure.

Default to the smallest change that solves the problem. Tight scope. No drive-by
edits. Minimal != timid (see P5 for when to go big).

- **Serves:** T3, Law 2 (small change = small new surface to keep legible).
- **Test (falsifiable):** a change touches files unrelated to its stated purpose
  -> FAIL. A "while I'm here" edit with no traced reason -> FAIL.
- **Conflict (vs P5):** resolved in P5. Sound structure -> minimal. Unsound
  structure -> restructure first, then minimal.

## P7 — Empiricism. No doctrine. Only live-verified metrics. (second-final)

There is no ideology, no belief — including these principles. Every claim verified
by live results and recorded metrics. Scaffold proof to the task: the right-sized
apparatus at the project's rigor tier (PROJECT.md §8). Live is the bar wherever a
live surface exists; where none exists (`deploy: none`, `prototype` tier), the bar
is the top reachable rung of the proof ladder (type > property > unit).

- **Serves:** T2, T7. Hardens "metrics OR live" to "live where it exists, scaffolded always."
- **Test (falsifiable):** a capability declared done on a claim, no recorded
  metric or live result behind it -> FAIL. A process claim (streaming, ordering,
  latency, recovery) proven by final output only -> FAIL. A threshold invented
  after the run -> FAIL.
- **Owner:** `verifier` builds the scaffold (harness, probe scripts, metric
  recording) appropriate to the tier. `developer` uses it; `bug_hunter` adds
  regression pins; `adversary` attacks. `verifier` builds the apparatus itself.
- **Conflict (vs speed/autonomy):** scaffold cost scales to stakes (P-rigor dial).
  Prototype -> a smoke script + types. Critical -> a live battery with recorded
  metrics. Never skip the bar; resize it.

## P8 — Aggressive culling. Extract the lesson, then cull the husk. (final)

Every loose script, one-off test, throwaway unblocker, convenience hack, stale
doc that does not enter the real codebase state is un-mapped debt. Two-step:
**(1) extract any lesson into durable seed context** (a protocol, an agent, the
three references, a comment, a ledger row — via
[protocols/iterative_context_evolution.md](protocols/iterative_context_evolution.md)),
**(2) then cull the carrier.** Nothing valuable lost; only the illegible husk dies.

- **Serves:** Law 2 (un-mapped state = decay), T10.
- **Test (falsifiable):** a script/test/doc with no further utility AND no recorded
  lesson, still in the tree -> FAIL. A cull that destroyed a lesson without
  recording it first -> FAIL. A spent scaffold (its metric no longer needed) left
  to rot -> FAIL.
- **Guard (do not over-cull):** a thing is cullable only when utility is spent AND
  lesson is recorded. Still produces a needed metric -> has utility -> stays.
  Looks loose but is a scaffold mid-build -> not spent -> stays. Cull the dead,
  never the in-flight.
- **Conflict (vs P7):** P7 builds scaffolds; P8 culls spent ones. No tension —
  they are one metabolism: build proof, harvest lesson, shed the husk. A scaffold
  lives exactly as long as its metric is needed.

---

## The metabolism (P7 + P8 together)

Verify everything live (P7) -> produces scaffolds + one-offs -> extract lessons,
cull husks (P8) -> leaving only verified, mapped, load-bearing state. Build proof,
harvest lesson, shed the rest. That is the heartbeat the first six principles serve.

## Using this doc

- Cite principles by number in findings (`P2 violation: removing X breaks Y`).
- A new rule in an agent/protocol traces to a principle or a law, or it dies.
- This doc itself obeys P7: a principle that stops producing measurable success
  is re-examined and cut. No principle is sacred (P5 applies to the doctrine too).
- Worked exemplars of these principles in code: [reference/PATTERNS.md](reference/PATTERNS.md)
  — seven language-agnostic patterns with self-proving example modules ("what
  good looks like").
