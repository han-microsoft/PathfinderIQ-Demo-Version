#!/usr/bin/env python3
"""graph — front door. Five verbs: build, verify, query, declare, resolve.

Not a god-script: routes to extractors (extract_*) + queries. Derived bands
regenerate from source; declared overlay preserved + merged; worklist tracked.
verify diffs derived-vs-source -> drift = exit 1 (stop-the-line honesty gate).

Usage: graph <build|verify|query|declare|resolve> [args]
Exit: 0 ok / 1 drift-or-fail / 2 usage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib as G  # noqa: E402
import schema  # noqa: E402
import queries as Q  # noqa: E402
import extract_py  # noqa: E402
import extract_md  # noqa: E402
import extract_sh  # noqa: E402
import extract_data  # noqa: E402

EXTRACTORS = [extract_py, extract_md, extract_sh, extract_data]


def _scope_paths(root: Path) -> list[str]:
    scope = G.binding("SCOPE_ROOT", ".") or "."
    base = (root / scope).resolve() if scope != "." else root
    return [str(p) for p in G.walk_files(base)]


def _run_extractors(root: Path):
    """Run all extractors over scope. Return (derived_records, worklist, coverage)."""
    paths = _scope_paths(root)
    derived: list[dict] = []
    worklist: list[dict] = []
    coverage: dict = {}
    for mod in EXTRACTORS:
        claimed = [p for p in paths if mod.claims(Path(p))] \
            if mod.CLAIM_SUFFIXES or mod is extract_sh else paths
        res = mod.extract(root, claimed if claimed else paths)
        derived.extend(res.records)
        worklist.extend(res.worklist)
        coverage.update(res.coverage)
    # de-dup nodes by id (extractors may emit shared ext nodes); keep first
    seen: set[str] = set()
    uniq: list[dict] = []
    for r in derived:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    return uniq, worklist, coverage


def _split(records):
    nodes = [r for r in records if "kind" in r and r["kind"] in schema.NODE_KINDS
             and "src" not in r]
    edges = [r for r in records if "src" in r]
    return nodes, edges


def cmd_build(root: Path, argv) -> int:
    gdir = G.graph_dir(root)
    derived, worklist, coverage = _run_extractors(root)
    overlay = G.load_jsonl(gdir / "overlay.jsonl")
    merged, collisions = G.merge_overlay(derived, overlay)
    nodes, edges = _split(merged)
    # prune worklist sites already closed by an agent-resolved overlay edge
    resolved = {tuple(r["attrs"]["site"]) for r in overlay
                if r.get("kind") == "calls" and "site" in r.get("attrs", {})}
    worklist = [w for w in worklist
                if (w["caller_id"], w["line"]) not in resolved]
    G.dump_jsonl(nodes, gdir / "nodes.jsonl")
    G.dump_jsonl(edges, gdir / "edges.jsonl")
    G.dump_worklist(worklist, gdir / "worklist.jsonl")
    coverage["calls_resolved"] = coverage.get("calls_resolved", 0) + len(resolved)
    coverage["calls_project"] = coverage.get("calls_project", 0) + len(resolved)
    coverage["calls_worklist"] = len(worklist)
    counts = {"nodes": len(nodes), "edges": len(edges),
              "overlay": len(overlay), "worklist": len(worklist)}
    G.write_manifest(gdir, counts, coverage, collisions)
    print(f"PASS build: {counts['nodes']} nodes, {counts['edges']} edges, "
          f"{counts['worklist']} worklist")
    cov = coverage
    if "calls_total" in cov:
        print(f"  calls: {cov['calls_resolved']}/{cov['calls_total']} resolved "
              f"({cov.get('calls_project', 0)} project + "
              f"{cov.get('calls_external', 0)} external), "
              f"{cov['calls_worklist']} worklist")
    return 0


def cmd_verify(root: Path, argv) -> int:
    gdir = G.graph_dir(root)
    if not (gdir / "nodes.jsonl").is_file():
        G.die("no snapshot: run 'graph build' first", 1)
    derived, worklist, _ = _run_extractors(root)
    fresh_nodes, fresh_edges = _split(derived)
    fresh = {r["id"]: r for r in [*fresh_nodes, *fresh_edges]}

    committed = G.load_jsonl(gdir / "nodes.jsonl") + G.load_jsonl(gdir / "edges.jsonl")
    comm_derived = {r["id"]: r for r in committed if r.get("band") == "derived"}
    comm_overlay = [r for r in committed if r.get("band") == "declared"]

    # attr keys the overlay injected into each derived record (id-match enrich):
    # strip them before the derived-vs-source diff so declared facts never read
    # as drift. Generic — not limited to any single key.
    overlay_src = G.load_jsonl(gdir / "overlay.jsonl")
    injected: dict[str, set] = {}
    for ov in overlay_src:
        injected.setdefault(ov["id"], set()).update(ov.get("attrs", {}).keys())

    drift = []
    fkeys, ckeys = set(fresh), set(comm_derived)
    for missing in sorted(ckeys - fkeys):
        drift.append(f"removed-in-source: {missing}")
    for added in sorted(fkeys - ckeys):
        drift.append(f"new-in-source: {added}")
    for k in sorted(fkeys & ckeys):
        f = json.dumps(_strip(fresh[k], injected.get(k, set())), sort_keys=True)
        c = json.dumps(_strip(comm_derived[k], injected.get(k, set())), sort_keys=True)
        if f != c:
            drift.append(f"changed: {k}")

    # dangling overlay: declared edge/node pointing at absent node
    all_ids = set(fresh) | {r["id"] for r in comm_overlay}
    for ov in comm_overlay:
        for end in ("src", "dst"):
            if end in ov and ov[end] not in all_ids:
                drift.append(f"dangling-overlay: {ov['id']} -> {ov[end]}")

    # worklist growth on changed files. Apply the same resolve-prune build does,
    # so an agent-resolved site never reads as a new unresolved call.
    resolved_sites = {tuple(r["attrs"]["site"]) for r in overlay_src
                      if r.get("kind") == "calls" and "site" in r.get("attrs", {})}
    old_wl = {(w["caller_id"], w["line"]) for w in G.load_jsonl(gdir / "worklist.jsonl")}
    new_wl = {(w["caller_id"], w["line"]) for w in worklist
              if (w["caller_id"], w["line"]) not in resolved_sites}
    grew = new_wl - old_wl
    for c, ln in sorted(grew):
        drift.append(f"new-unresolved-call: {c}:{ln}")

    if drift:
        for d in drift:
            print(d)
        print(f"FAIL verify: {len(drift)} drift (snapshot stale -> rebuild + commit)")
        return 1
    print("PASS verify: snapshot matches source")
    return 0


def _strip(r, keys):
    """Drop the named overlay-injected attr keys for a clean derived-vs-source diff."""
    c = dict(r)
    a = {k: v for k, v in c.get("attrs", {}).items() if k not in keys}
    c["attrs"] = a
    return c


def _load_model(root: Path) -> Q.Model:
    gdir = G.graph_dir(root)
    return Q.Model(G.load_jsonl(gdir / "nodes.jsonl"),
                   G.load_jsonl(gdir / "edges.jsonl"))


def cmd_query(root: Path, argv) -> int:
    if not argv:
        G.die("usage: graph query <name> [args]  (names: "
              + ", ".join(sorted(Q.QUERIES)) + ")")
    name, args = argv[0], argv[1:]
    fn = Q.QUERIES.get(name)
    if not fn:
        G.die(f"unknown query '{name}'", 2)
    m = _load_model(root)
    lines, ok = fn(m, args)
    for ln in lines:
        print(ln)
    return 0 if ok else 1


def cmd_declare(root: Path, argv) -> int:
    if not argv:
        G.die('usage: graph declare \'{"id":...,"band":"declared",...}\'')
    rec = json.loads(argv[0])
    rec.setdefault("band", "declared")
    rec.setdefault("source", "declare")
    rec.setdefault("attrs", {})
    errs = (schema.validate_edge(rec) if "src" in rec
            else schema.validate_node(rec))
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 2
    if rec["band"] != "declared":
        G.die("declare only writes band=declared records", 2)
    gdir = G.graph_dir(root)
    overlay = G.load_jsonl(gdir / "overlay.jsonl")
    overlay = [r for r in overlay if r["id"] != rec["id"]]
    overlay.append(rec)
    G.dump_jsonl(overlay, gdir / "overlay.jsonl")
    print(f"PASS declare: {rec['id']} ({len(overlay)} overlay records)")
    return 0


def cmd_resolve(root: Path, argv) -> int:
    if len(argv) < 2:
        G.die("usage: graph resolve <caller_id:line> <dst_id>")
    site, dst = argv[0], argv[1]
    caller, _, line = site.rpartition(":")
    gdir = G.graph_dir(root)
    wl = G.load_jsonl(gdir / "worklist.jsonl")
    match = [w for w in wl
             if w["caller_id"] == caller and str(w["line"]) == line]
    if not match:
        G.die(f"no open worklist site {site}", 1)
    e = G.edge("calls", caller, dst, source="agent",
               attrs={"confidence": "high", "resolver": "agent",
                      "site": [caller, int(line)]})
    e["band"] = "declared"
    overlay = G.load_jsonl(gdir / "overlay.jsonl")
    overlay = [r for r in overlay if r["id"] != e["id"]]
    overlay.append(e)
    G.dump_jsonl(overlay, gdir / "overlay.jsonl")
    wl = [w for w in wl if not (w["caller_id"] == caller and str(w["line"]) == line)]
    G.dump_worklist(wl, gdir / "worklist.jsonl")
    print(f"PASS resolve: {site} -> {dst} ({len(wl)} worklist remain)")
    return 0


VERBS = {"build": cmd_build, "verify": cmd_verify, "query": cmd_query,
         "declare": cmd_declare, "resolve": cmd_resolve}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in VERBS:
        G.die("usage: graph <build|verify|query|declare|resolve> [args]")
    root = G.find_repo_root()
    return VERBS[argv[0]](root, argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
