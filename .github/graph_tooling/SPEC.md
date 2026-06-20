# graph_tooling — SPEC

Self-verifying code model. One queryable graph of the whole codebase — files,
modules, functions, classes, docs, scripts, data assets, third-party deps — and
the dependency edges between them. Law 1 made literal: whole-system true-state in
one model. Law 2 honoured: graph is *derived + diff-verified*, so it cannot
silently drift past the gate.

Not a thirteenth `agent_tooling` sibling. A **substrate**. `cycle_scan`,
`dup_scan`, `module_size` collapse into queries over this one model once it
exists.

## Prime directive: derive, don't declare. Then diff to verify.

Hand-maintained graph = second source of truth = decays faster than docs (Law 2
violation). Forbidden. Instead:

- **Derived band** (~90%): imports, defs, calls, contains, links — extracted from
  source by AST/parsers, deterministically. Nobody hand-edits. `graph build`
  regenerates wholesale.
- **Declared band** (~10%): semantic facts no parser knows — core-vs-leaf
  dependency role, data-asset flows, functionality tags. Thin overlay. Written
  only through the `graph declare` command, never raw.
- **Honesty enforcer**: committed snapshot in repo. `graph build` regenerates.
  `graph verify` diffs regenerated-vs-committed → drift = nonzero exit =
  stop-the-line. Graph self-checks like a type. Agents do not *remember* to
  update it; the gate *forces* it.

## Binding contract (every tool obeys)

Inherits `agent_tooling/SPEC.md` contract verbatim. Restated load-bearing points:

- **Zero deps.** Python 3 stdlib only. No pip. No bash beyond POSIX `sh`.
- **One job each (P1/P2).** Shared logic flows from `lib.py` (graph_tooling) and
  reuses `agent_tooling/lib.py` for bindings parse + bounded walk + `--json`
  envelope. No re-home of those primitives (C1).
- **Read-only by default.** Extractors + queries read. Only `build`, `declare`,
  `resolve` write — and only to `graph/`.
- **Exit code = verdict.** `0` pass, `1` violation/drift/fail, `2` usage/internal.
  So `graph verify` doubles as a CI/gate check.
- **Deterministic (P4).** Same source → byte-identical snapshot → same exit. No
  clock in any verify-relevant output. Build timestamp is informational, excluded
  from the diff.
- **Resolve, never hardcode.** Project facts via `project get <KEY>`. Scope root,
  ignore set, config module resolve from PROJECT.md §0.
- **Bounded.** Shared ignore set: no walk into `.git`, `node_modules`, `.venv`,
  `__pycache__`, `dist`, `build`, `*.lock`, binary blobs.

## Language choice rule

Python throughout. All stages parse, build AST, do cross-file analysis — past the
bash threshold by definition. No shell tool in this suite.

---

## Schema

Two universal record types — **node**, **edge**. Flat object. Fixed spine =
standardized interface. Open `attrs` bag = extensibility. New information goes in
`attrs` or as a new `kind` value. **Never** a new top-level field. That rule keeps
the model extensible without migration.

### Node spine

```jsonc
{
  "id":     "py:func:agent_tooling/lib.py#find_repo_root", // deterministic, structured
  "kind":   "function",        // controlled vocab (extensible)
  "lang":   "python",          // python|markdown|shell|data|none
  "path":   "agent_tooling/lib.py",
  "span":   [12, 47],          // [start,end] lines, or null. May drift; not in id.
  "name":   "find_repo_root",
  "band":   "derived",         // derived|declared
  "source": "py_extractor",    // minting tool
  "attrs":  {}                 // open: loc, complexity, dup_group, tags...
}
```

### Edge spine

```jsonc
{
  "id":     "calls:agent_tooling/cycle_scan.py#main->agent_tooling/lib.py#walk",
  "kind":   "calls",           // controlled vocab (extensible)
  "src":    "<node id>",
  "dst":    "<node id>",
  "band":   "derived",
  "source": "py_extractor",
  "attrs":  {}                 // open: role, confidence, resolver, candidates, line...
}
```

### Worklist entry (not a graph record — pending work)

```jsonc
{ "caller_id":"<id>", "callee_name":"foo", "line":88, "arity":2,
  "reason":"ambiguous|dynamic|external|unknown", "status":"open" }
```

Worklist lives outside nodes/edges. Only resolved facts enter the graph. Pending
truth is not asserted truth.

### The `id` is the contract

Single most load-bearing decision. Invariants:

- **Deterministic** — same source → same id, always (P4). No content hash, no
  timestamp, no counter.
- **Structured** — `<lang>:<kind>:<path>#<qualifier>`. Parseable back into parts;
  queries filter on id without a side table.
- **Stable under benign change** — blank line above a function must not change its
  id. Id uses qualified name path, never line number. Line lives in `span`, which
  may drift.

Id stability is the keystone. `graph build` regenerates ids deterministically;
`graph verify` diffs id-sets. Deleted function → id vanishes → drift caught.
Nondeterministic id → verify flaps forever. So: **id stability is invariant zero.**

Id grammar by kind:

```text
py:module:path/to/file.py
py:func:path/to/file.py#name
py:func:path/to/file.py#Class.method
py:class:path/to/file.py#Class
md:doc:README.md
md:heading:README.md#slugified-heading
sh:script:deploy.sh
data:asset:fixtures/sample.json
ext:pkg:requests                 // third-party, never expanded
ext:module:requests.adapters
```

### Controlled vocabularies (one home, versioned)

`kind`, `lang`, `band` are enums defined once in `schema.py`. Extend = append to
vocab, never restructure. `schema.py` carries `SCHEMA_VERSION`. Snapshot records
the version it built under. Mismatch → `verify` says rebuild, never silently
misreads. That is the migration safety.

Node kinds (seed set):

```text
file module package function method class
doc heading script data_asset config_key external
```

Edge kinds (seed set):

```text
contains   # backbone tree: file contains func, package contains module, doc contains heading
imports    # module-level import (reliable)
calls      # call-site -> def (best-effort, confidence-tagged)
defines    # scope defines symbol
references # name use, non-call
links      # md link -> target
invokes    # script -> script / script -> binary
reads_config  # code -> config_key
depends_on # node -> external pkg
declared_dep   # overlay: marks a dependency role (core/optional/dev/runtime)
declared_leaf  # overlay: marks an optional-leaf boundary (P2)
```

`contains` is the spine — gives the tree. The rest give the cross-cutting web.

### Band semantics (per-record, first-class)

`band` on every record drives the honesty check:

- **derived** — regenerated wholesale each build. `verify` diffs against snapshot.
  Drift = stop-the-line.
- **declared** — preserved across builds. `verify` checks referential integrity
  only: declared edge → deleted node = dangling = error.

Without per-record `band`, "regenerate this" vs "preserve this" can't be
mechanically separated. `band` makes the two-band model operational.

### Edge enrichment (Q2: edges carry semantic load)

Derived band states the edge *exists*. Declared band states what it *means*.

- A real import is born `derived` (`kind: imports`, `attrs:{}`).
- Overlay enriches it by **id-match**: a declared record with the same id adds
  `attrs.role: core`. Merge at build.
- Result: "what is a core dependency" = query edges where `attrs.role==core`,
  grouped by `dst` external node.

Merge rule (deterministic): derived applied first; overlay `attrs` win on key
collision; collision logged to manifest. Overlay may **enrich** (id-match) or
**introduce** a pure-declared node/edge (new id, `band: declared`).

### `attrs` discipline: facts stored, metrics computed

- Extractors store only **observed facts** in `attrs`: `loc`, `complexity`,
  `span` detail, `dup_group`, `line`.
- Queries **compute** metrics on the fly — never store them. Fan-in =
  `count(edges where dst==node)`. Always fresh. A stored metric is a third source
  of truth that rots.

Convention: flat keys (`loc`, `dup_group`); prefix by tool on collision
(`dup.group`).

---

## The `calls` resolution pipeline (tagger → resolver → worklist → agent)

`calls` is the lying-map risk. Explicit machinery. Every `calls` edge carries
`attrs.confidence` + `attrs.resolver`.

**Stage 1 — Tagger (deterministic, exhaustive).** Walk AST, find every call
expression. Emit one call-site `{caller_id, callee_name, line, arity}` per
occurrence. Complete by construction — finds *where*, not yet *what*. This makes
the denominator honest.

**Stage 2 — Best-effort resolver (deterministic).** Bind `callee_name` → node id
via import table + local scope + qualified name. Outcomes per site:

- **resolved-project** → `calls` edge to a project node, `confidence: high`.
- **resolved-external** → call binds to no project def/builtin/import: a library
  or instance method (`str.lower`, `Path.resolve`, `list.append`). Edge to an
  `ext:method:<name>` node, `resolver: external`. Not an agent task — provably not
  a project call (callee name matches no project definition).
- **ambiguous** (callee name matches a project def but >1 candidate, or a
  name-collision like `read_text` vs `Path.read_text`) → **worklist entry**.
- **dynamic** (no callee name: `getattr`, chained call) → **worklist entry**.

**Stage 3 — Agent fallback.** Worklist = agent queue. Agent reads code, binds via
`graph resolve` → edge `confidence: high`, `resolver: agent`.

Honesty guarantees (T4 max-error-visibility applied to the graph):

- Tagger output = denominator. Build reports the split: `calls: 969/977 resolved
  (249 project + 720 external), 8 worklist`. Project-internal call graph is the
  signal; external = bound out of project; worklist = genuine agent candidates
  only (name-collision, multi-target, pure-dynamic). Graph knows what it does not
  know.
- Worklist holds only what an agent could plausibly bind to a project node. A
  library method is resolved-external, never a fake task — keeps the metric honest
  (no penalty for the stdlib existing) and the queue real.
- `verify` fails if worklist grew on changed files but was not addressed — new
  unresolved calls = stop-the-line, same class as a new lint failure.

Pattern generalizes to any hard edge (dynamic import, data-asset flow,
config-key reference): tagger → resolver → worklist → agent. One shape, reused.

---

## The suite

### Engine + schema

| Tool | Lang | Job | Exit |
| --- | --- | --- | --- |
| `schema` | py | One home for vocab (`kind`/`lang`/`band`), `SCHEMA_VERSION`, spine validator. `schema validate graph/` checks every record against the spine. Imported by every other tool. | 0 / 1 / 2 |
| `lib` | py | graph_tooling shared: load/dump sorted JSONL, id grammar build+parse, record merge, manifest read/write. Reuses `agent_tooling/lib.py` for bindings + walk + envelope. No duplicate (C1). | — |

### Extractors (derive the model)

| Tool | Lang | Job | Exit |
| --- | --- | --- | --- |
| `extract_py` | py | Python nodes+edges: module/func/method/class, `contains`, `imports`, `defines`, `references`, `depends_on`. Calls via tagger+resolver. `assumes:` Python; declares coverage. | 0 / 2 |
| `extract_md` | py | Markdown nodes: `doc`, `heading`; edges: `contains`, `links`. Link target resolved to node id where in-repo, else `ext`. | 0 / 2 |
| `extract_sh` | py | Shell scripts: `script` nodes, `invokes` edges (script→script, script→binary). Best-effort; declares coverage. | 0 / 2 |
| `extract_data` | py | `data_asset` nodes from declared globs (PROJECT.md-bound). No edges derived; flows are declared band. | 0 / 2 |

Extractor interface — one signature, registered by extension + `claims()`
predicate:

```python
def extract(root: str, paths: list[str]) -> Iterable[Record]: ...
```

New language = drop in `extract_<lang>.py`, register extensions. Zero change
elsewhere. That is the extensibility guarantee.

### Commands (the standardized interface)

| Tool | Lang | Job | Exit |
| --- | --- | --- | --- |
| `graph` | py | Front door. Dispatches the five verbs. Not a god-script — routes to the suite. | 0 / 1 / 2 |

```text
graph build                 # run extractors -> derived bands; preserve overlay;
                            #   merge enrichments; refresh worklist; rewrite manifest
graph verify                # diff derived vs source; dangling-overlay check;
                            #   worklist-growth check -> exit 1 on any drift
graph query <name> [args]   # analytics over loaded model (see below)
graph declare <rec-json>    # append ONE validated overlay record (only CRUD write)
graph resolve <site> <id>   # close a worklist entry -> high-confidence agent edge
```

### Queries (analytics over one model)

| Query | Job (principle) |
| --- | --- |
| `fanin <id>` / `fanout <id>` | Coupling. Inbound/outbound edge count + list. |
| `coredeps` | External nodes ranked by inbound `depends_on`; cross-ref `attrs.role` (P2). |
| `cycles` | Tarjan SCC over `imports`/`depends_on` (P1 DAG). Replaces `cycle_scan`. |
| `dead` | Nodes with zero inbound non-`contains` edges (undertaker reachability). |
| `orphans` | `doc` nodes with zero inbound `links`. |
| `dups` | Nodes sharing `attrs.dup_group` (P1). Replaces `dup_scan` reporting. |
| `boundary` | Edges crossing a declared boundary (`declared_leaf`/config module). Generalizes `boundary_check`. |
| `path <a> <b>` | Dependency path between two nodes, or none. |
| `impact <node\|path> ... [--depth N]` | Reverse reachability blast radius; accepts file paths (compose with `changed.sh` for diff scope). |

Each query = `query(graph) -> Result` over the loaded model. Never re-walks the
filesystem. New analytic = sibling function. Same signature.

### Shared

| File | Job |
| --- | --- |
| `lib.py` | See engine table. The one home for graph IO + id grammar + merge. |

---

## Storage (project snapshot)

Diff-friendly, deterministic, stdlib-parseable. JSONL, one record per line,
**sorted by id**, sorted keys, no trailing whitespace → byte-identical on
identical source → clean git diff → real `verify` via plain diff.

```text
graph/
  manifest.json    # schema_version, coverage %, extractor versions, counts, merge-collision log
  nodes.jsonl      # derived nodes, sorted by id
  edges.jsonl      # derived edges, sorted by id
  overlay.jsonl    # declared band: enrichments + pure-declared (graph declare only)
  worklist.jsonl   # open unresolved sites — agent queue
```

Shard derived files per top-level package when one file invites merge conflict.
JSONL over one JSON: append-friendly, line-diffable, streamable in stdlib, one
malformed line does not poison the file.

## Seed vs project split

- Seed ships the **engine**: `schema.py`, `lib.py`, extractors, queries, `graph`.
  Language-agnostic, role-resolved from PROJECT.md.
- Project ships the **snapshot**: `graph/*.jsonl` + `manifest.json`. Regenerated
  on build. Same principles-vs-instance split as the rest of the seed.

## Cross-cutting behaviour

- **Self-application (P7).** Run against this seed repo: `graph build` then
  `graph verify` exits 0. Suite proves itself on its own source.
- **`graph verify` is a gate.** Wire into the regression protocol: any change that
  touches code must leave `verify` green (snapshot regenerated + committed, or
  worklist addressed).
- **Consolidation, not addition (Law 2).** `cycle_scan`, `dup_scan`,
  `module_size`, `boundary_check` refactor to query this model post-build.
  `unknown:` exact retirement sequence — settle when graph queries reach parity.

## Discoverability

- One line in `copilot-instructions.md` points agents at `graph_tooling/`.
- `graph_tooling/README.md` indexes engine, extractors, commands, queries: name,
  one-line job, principle served.
- `cartographer` owns the map: seeds it, resolves the worklist, declares the
  semantic overlay, repairs drift ([../agents/cartographer.agent.md](../agents/cartographer.agent.md)).
- Every agent that edits code runs `graph build` + `graph verify` before
  completion. Wired into regression + housekeeping protocols.

## Open / deferred

- `unknown:` retirement order for the four analyzers superseded by queries —
  decide at parity, not now.
- `assumes:` per-language extractor coverage is best-effort; each declares its
  coverage in the manifest. Graph must know what it does not know.
- `calls` ships with tagger+resolver+worklist from v1 (all edges, per decision).
  Same pipeline extends to data-asset flow + config-key edges when those pay.

## Acceptance (this build)

```text
graph_tooling COMPLETE -- schema + lib + 4 extractors + graph(5 verbs) + 9 queries,
zero deps, every tool exit-coded, build->verify green on seed snapshot,
calls coverage reported with worklist, discoverability wired
```
