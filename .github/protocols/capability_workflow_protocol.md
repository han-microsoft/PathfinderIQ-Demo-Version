# Capability Workflow Protocol

How to design, build, and verify a **capability workflow**: a flow where a single
minimal operator instruction is resolved entirely by the agent — it **searches**
for the capability it needs, **instantiates or reuses** scoped subagents, **finds
and executes a skill** through them, and produces a **verified artifact**. The
canonical example is "give a blob + 'prep for diagnosis' → a diagnostic AI Search
knowledge base" ([build_spec/orchestrator_20260617_capability_fabric.md](../../build_spec/orchestrator_20260617_capability_fabric.md)
END-GOAL). This protocol generalises that to any control-room / rapid-actioning
domain.

Binds to: [evidence_protocol.md](evidence_protocol.md) (pre-flight),
[regression_protocol.md](regression_protocol.md) (live sweep),
[data_workflow_acceptance_protocol.md](data_workflow_acceptance_protocol.md)
(DAA acceptance). Capability artifacts live as files ∪ Cosmos overlay per the
agents-as-files pattern.

## 0. When this protocol applies

Use it when a capability must be reachable from a **minimal instruction** with no
tool/skill hand-holding — i.e. the agent must discover and assemble the capability
itself. Do NOT use it for a one-off scripted task (use a probe) or a fixed pipeline
(use the DAA workflow registry).

## 1. The five layers a capability workflow must satisfy

A capability workflow is complete only when ALL five resolve the same intent:

1. **Skill (the playbook)** — a domain-blind `SKILL.md` + manifest describing the
   process: inputs, the tool sequence, the bounding/safety rules, the success
   criterion. Searchable, tagged, baked ∪ durable.
2. **Tools / recipes (the executors)** — the typed tools the skill sequences, or a
   recipe that composes them. Every tool the skill names is real and ceiling-legal.
3. **Search (the discovery)** — `find_skills`/`find_tools`/`find_recipes`/
   `find_agents` over the catalog return this capability for the intent's natural
   phrasing (NOT the artifact's internal name). Tagged so the taxonomy finds it.
4. **Agent (the executor persona)** — the lean orchestrator can mint a scoped
   subagent (tools + the skill's SKILL.md as instructions) OR reuse a shipped/
   cached one; the subagent's lens ⊆ the orchestrator's ceiling.
5. **Artifact + verification (the proof)** — a durable, independently-queryable
   result that meets the domain bar (e.g. a vector index whose diagnostic query
   returns the correct records), retrievable AFTER the run by a separate read.

A workflow that passes only the final artifact check but where the agent could not
DISCOVER the capability from the minimal instruction has FAILED layer 3 — the most
common gap.

## 2. Design steps (author a new capability workflow)

1. **Name the intent, not the data.** Phrase the skill + tags for the operator's
   words ("prep for diagnosis", "make searchable", "build a knowledge base"), not
   the dataset. Domain-blind: any corpus, any industry.
2. **Write the skill** per [authoring_skills guide](../../docs/guides/authoring_skills.md):
   manifest (`allowed_tools` ⊆ the executor's ceiling, `tags`, `summary`) +
   `SKILL.md` (numbered playbook, the live-learned rules baked in — bounding,
   nonce/scratch namespaces, confirmation, no-download).
3. **Provide the executors.** Reuse existing typed tools; add a recipe only if a
   fixed multi-tool sequence is reused. Never mint a new privileged adapter.
4. **Make it discoverable.** Add catalog tags so `find_*` returns it for the
   intent phrasing. Verify with a real `find_skills('<operator phrasing>')` call.
5. **Define the subagent shape.** What lens (tools + instructions) does the
   orchestrator grant a subagent to run this? Keep it minimal + ceiling-legal.
6. **Declare the verification.** The exact post-run read that proves the artifact
   meets the bar (the query + expected-result predicate), runnable independently.

## 3. Build + gate (per phase)

- Local gate before any deploy: `py_compile`, the affected `pytest`, `npm run
  build` + vitest for UI, `validate_skills.py`, `graph build && graph verify`.
- Deploy only via `deploy_vm_agent.sh`; after deploy poll `healthz.image_sha`.
- A new write tool an agent must self-confirm needs `confirmation` in its
  model-facing schema (the MAF bridge injects it for `risk=write` — see AUTODEV).
- An agent-authored skill/recipe/agent's referenced tools MUST be ⊆ the authoring
  turn's lens (no escalation), wildcard refused, baked ids immutable, audited.

## 4. Live acceptance (the minimal-instruction test)

Drive the deployed app as a **human user only** — one chat turn carrying the
minimal instruction, no direct tool invokes for the work. Then verify the artifact
by an independent signed read. The trace MUST show, in order:

1. a capability **search** (`find_*`) for the intent;
2. a subagent **instantiated or reused** (`agents.write`/`agents.dispatch`);
3. the **skill** as the executed playbook (its tools run through the subagent);
4. the **artifact** verified by an independent query meeting the domain bar.

Record the marker + `_snapshots/<workflow>_e2e_<nonce>.json` (tool trace + artifact
id + verification results). Final-output-only proof is insufficient — the trace
must show discovery + instantiation + skill execution, not a hardcoded path.

## 5. Failure triage

| Symptom | Likely layer | Fix |
|---|---|---|
| agent never finds the capability | 3 search/tags | add intent-phrased tags; verify `find_skills` |
| agent hardcodes tools, skips search | 4 orchestrator lens | orchestrator must be lean (meta-tools only) so it MUST search |
| `confirmation_required` loop | executor | confirmation in model-facing schema (bridge) |
| `*_not_allowed` / `target_not_allowed` | executor gating | reads = account/RBAC scope; writes = nonce/scratch namespace |
| artifact empty / key error | executor | bound the corpus to the window; valid document keys |
| subagent `agent_not_found` | 4 dispatch | dispatch resolves baked ∪ caller durable roster |
| escalation (subagent has tool author lacks) | safety | authored lens ⊆ authoring ceiling |

## 6. Pay-forward

Every new capability workflow updates: CURRENT_STATE (capability row + marker),
FEATURES (skill/tool/recipe counts), the authoring guide if the contract changed,
and AUTODEV for any live-found landmine. A recurring capability becomes a shipped
baked skill + recipe; a one-off stays a probe.
