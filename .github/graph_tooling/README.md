# graph_tooling

Self-verifying code knowledge-graph. One queryable model of the whole codebase —
files, modules, functions, classes, docs, scripts, data assets, third-party deps
— plus the dependency edges between them. Spec: [SPEC.md](SPEC.md).

Law 1: whole-system true-state in one model. Law 2: derived + diff-verified, so
the graph cannot silently drift past the gate.

Owned by `cartographer` ([../agents/cartographer.agent.md](../agents/cartographer.agent.md))
— the LLM agent that seeds the map, resolves the worklist, declares the semantic
overlay, and repairs drift. The engine derives; the agent resolves the residue.

## Quick start

```sh
python3 .github/graph_tooling/graph.py build      # regenerate snapshot -> graph/
python3 .github/graph_tooling/graph.py verify     # drift vs source -> exit 1 on drift
python3 .github/graph_tooling/graph.py query cycles
```

Snapshot lands in `graph/` at repo root: `nodes.jsonl`, `edges.jsonl`,
`overlay.jsonl`, `worklist.jsonl`, `manifest.json`.

## Two bands

- **Derived** (~90%) — extracted from source deterministically. Regenerated whole
  each `build`. Nobody hand-edits. `verify` diffs vs source; drift = stop-the-line.
- **Declared** (~10%) — semantic facts no parser knows (core-vs-leaf dep role,
  data flows). Written only via `graph declare`. Preserved across builds; `verify`
  checks referential integrity.

## Commands

| Verb | Job | Exit |
| --- | --- | --- |
| `build` | Run extractors -> derived bands; merge overlay; refresh worklist; rewrite manifest. | 0 / 2 |
| `verify` | Diff derived vs source; dangling-overlay; worklist growth -> 1 on drift. Gate check. | 0 / 1 |
| `query <name> [args]` | Analytics over the loaded model. | 0 / 1 |
| `declare '<json>'` | Append one validated `band=declared` overlay record. Only CRUD write. | 0 / 2 |
| `resolve <caller:line> <dst>` | Close a worklist site -> high-confidence agent calls edge. | 0 / 1 |

## Queries

| Name | Job |
| --- | --- |
| `fanin <id>` / `fanout <id>` | Coupling: inbound/outbound edges. |
| `coredeps` | External nodes ranked by inbound deps; shows `attrs.role`. |
| `cycles` | Import-cycle SCC (P1 DAG). |
| `dead` | Functions/classes with no non-`contains` inbound (reachability). |
| `orphans` | Docs with no inbound `links`. |
| `dups` | Nodes sharing `attrs.dup_group`. |
| `boundary` | Edges crossing a declared-leaf boundary (P2). |
| `path <a> <b>` | Dependency path between two nodes. |
| `impact <node\|path> [...] [--depth N]` | Blast radius: everything transitively depending on a node/file. Scopes a change + its regression. |

## Diff-scoped impact (the "what breaks if I change my diff?" recipe)

`impact` accepts file paths and multiple seeds, so compose it with `changed.sh`
to get the blast radius of an uncommitted diff:

```sh
# union blast radius of every changed file, direct dependents only
python3 .github/graph_tooling/graph.py query impact \
    $(sh .github/agent_tooling/changed.sh --names) --depth 1
```

Use it before editing (plan a minimal-blast change) and to scope regression (test
the impacted set, not the whole repo). Unmapped files (e.g. `.pyc`, data blobs)
are reported as `unresolved`, never silently dropped (T4).

Note: `run_all.py` stays whole-repo by design — whole-graph audits (`dup_scan`,
`cycle_scan`, `graph verify`) cannot be partial without masking results, and the
suite runs in well under a second. `impact` is the diff-scoping tool; the audit
sweep is not.

## Engine

| File | Job |
| --- | --- |
| [schema.py](schema.py) | Vocab (`kind`/`lang`/`band`), `SCHEMA_VERSION`, spine validator. One home. |
| [lib.py](lib.py) | Graph IO (sorted JSONL), id grammar, overlay merge, manifest. Reuses `agent_tooling/lib.py`. |
| [extract_py.py](extract_py.py) | Python nodes/edges; calls via tagger -> resolver -> worklist. |
| [extract_md.py](extract_md.py) | Doc/heading nodes; contains/links edges. |
| [extract_sh.py](extract_sh.py) | Script nodes; invokes edges. |
| [extract_data.py](extract_data.py) | Data-asset nodes from `GRAPH_DATA_GLOBS`. |
| [queries.py](queries.py) | The nine analytics over one loaded model. |
| [graph.py](graph.py) | Front door; routes the five verbs. |

## `calls` resolution (honest by construction)

Tagger finds every call site (exhaustive denominator). Resolver binds what it
safely can: **resolved** (high), **ambiguous** (low + candidates), **unresolved**
(worklist, no fake edge). Agent closes worklist via `graph resolve`. Three
queryable states; no silent guess. Coverage reported in `manifest.json`.

## Extending

- New language: add `extract_<lang>.py` with `claims(path)` + `extract(root, paths)
  -> ExtractResult`, register in `graph.py` `EXTRACTORS`. Zero change elsewhere.
- New analytic: add `q_<name>` to `queries.py`, register in `QUERIES`.
- New node/edge kind: append to the vocab in `schema.py`. Never add a top-level
  field — extend via `attrs`.

## Binding

- Snapshot scope = `SCOPE_ROOT` (PROJECT.md §0; default repo root).
- Data assets = `GRAPH_DATA_GLOBS` (comma globs; unset -> skipped).
- Zero deps, stdlib only. Deterministic: same source -> byte-identical snapshot.
