"""queries — analytics over the loaded graph model. Read-only.

Each query: fn(model, args) -> (lines, ok). Never walks the filesystem.
Absorbs cycle_scan / dup_scan reporting / module_size / boundary_check.
"""
from __future__ import annotations


class Model:
    def __init__(self, nodes: list[dict], edges: list[dict]):
        self.nodes = {n["id"]: n for n in nodes}
        self.edges = edges
        self.out: dict[str, list[dict]] = {}
        self.inn: dict[str, list[dict]] = {}
        for e in edges:
            self.out.setdefault(e["src"], []).append(e)
            self.inn.setdefault(e["dst"], []).append(e)

    def fanout(self, nid, kinds=None):
        return [e for e in self.out.get(nid, []) if not kinds or e["kind"] in kinds]

    def fanin(self, nid, kinds=None):
        return [e for e in self.inn.get(nid, []) if not kinds or e["kind"] in kinds]


def q_fanin(m: Model, args):
    nid = args[0]
    es = m.fanin(nid)
    lines = [f"{e['kind']} <- {e['src']}" for e in es]
    return [f"fanin {nid}: {len(es)}", *lines], True


def q_fanout(m: Model, args):
    nid = args[0]
    es = m.fanout(nid)
    lines = [f"{e['kind']} -> {e['dst']}" for e in es]
    return [f"fanout {nid}: {len(es)}", *lines], True


def q_coredeps(m: Model, args):
    rows = []
    for nid, n in m.nodes.items():
        if n["kind"] != "external":
            continue
        deps = m.fanin(nid, ("depends_on", "imports", "calls", "invokes"))
        if not deps:
            continue
        roles = sorted({e["attrs"].get("role", "-") for e in deps})
        rows.append((len(deps), nid, ",".join(roles)))
    rows.sort(reverse=True)
    lines = [f"{c:4d}  {nid}  role={r}" for c, nid, r in rows]
    return [f"external deps: {len(rows)}", *lines], True


def _tarjan(nodes, succ):
    idx = {}
    low = {}
    onstk = {}
    stk = []
    counter = [0]
    sccs = []

    def strong(v):
        idx[v] = low[v] = counter[0]
        counter[0] += 1
        stk.append(v)
        onstk[v] = True
        for w in succ.get(v, ()):
            if w not in idx:
                strong(w)
                low[v] = min(low[v], low[w])
            elif onstk.get(w):
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stk.pop()
                onstk[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(comp)

    import sys
    sys.setrecursionlimit(10000)
    for v in nodes:
        if v not in idx:
            strong(v)
    return sccs


def q_cycles(m: Model, args):
    succ: dict[str, list[str]] = {}
    mods = [nid for nid, n in m.nodes.items() if n["kind"] == "module"]
    for e in m.edges:
        if e["kind"] == "imports":
            succ.setdefault(e["src"], []).append(e["dst"])
    sccs = _tarjan(mods, succ)
    lines = []
    for comp in sccs:
        lines.append("cycle: " + " -> ".join(comp))
    ok = not sccs
    return [f"import cycles: {len(sccs)}", *lines], ok


def q_dead(m: Model, args):
    rows = []
    for nid, n in m.nodes.items():
        if n["kind"] not in ("function", "method", "class"):
            continue
        inbound = [e for e in m.fanin(nid) if e["kind"] != "contains"]
        if not inbound:
            rows.append(nid)
    rows.sort()
    return [f"dead (no non-contains inbound): {len(rows)}", *rows], True


def q_orphans(m: Model, args):
    rows = []
    for nid, n in m.nodes.items():
        if n["kind"] != "doc":
            continue
        if not m.fanin(nid, ("links",)):
            rows.append(nid)
    rows.sort()
    return [f"orphan docs: {len(rows)}", *rows], True


def q_dups(m: Model, args):
    groups: dict[str, list[str]] = {}
    for nid, n in m.nodes.items():
        g = n["attrs"].get("dup_group")
        if g:
            groups.setdefault(g, []).append(nid)
    rows = [(g, ids) for g, ids in groups.items() if len(ids) > 1]
    lines = []
    for g, ids in sorted(rows):
        lines.append(f"group {g}: " + ", ".join(sorted(ids)))
    return [f"dup groups: {len(rows)}", *lines], True


def q_boundary(m: Model, args):
    """Edges crossing a declared_leaf boundary node (P2)."""
    leaves = {e["dst"] for e in m.edges if e["kind"] == "declared_leaf"}
    leaves |= {e["src"] for e in m.edges if e["kind"] == "declared_leaf"}
    rows = []
    for e in m.edges:
        if e["kind"] in ("declared_leaf", "declared_dep"):
            continue
        if e["src"] in leaves or e["dst"] in leaves:
            rows.append(f"{e['kind']} {e['src']} -> {e['dst']}")
    rows.sort()
    return [f"boundary-crossing edges: {len(rows)}", *rows], True


def q_path(m: Model, args):
    a, b = args[0], args[1]
    from collections import deque
    prev = {a: None}
    dq = deque([a])
    while dq:
        cur = dq.popleft()
        if cur == b:
            break
        for e in m.out.get(cur, []):
            if e["dst"] not in prev:
                prev[e["dst"]] = cur
                dq.append(e["dst"])
    if b not in prev:
        return [f"no path {a} -> {b}"], True
    chain = []
    cur = b
    while cur is not None:
        chain.append(cur)
        cur = prev[cur]
    return [" -> ".join(reversed(chain))], True


def q_impact(m: Model, args):
    """Blast radius: everything transitively depending on a node or file.

    Reverse reachability over calls/imports/contains/invokes/depends_on. Answers
    "if I change X, what could break?" — scopes a minimal change + its regression.

        graph query impact <node-id|path> [<node-id|path> ...] [--depth N]

    A path arg (e.g. a changed file from `changed.sh --names`) resolves to every
    node in that file; pass several to get the union blast radius of a diff.
    """
    from collections import deque
    depth_cap = None
    pos: list[str] = []
    skip = False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a == "--depth":
            if i + 1 < len(args):
                depth_cap = int(args[i + 1])
                skip = True
            continue
        if a.startswith("--"):
            continue
        pos.append(a)
    if not pos:
        return ["usage: graph query impact <node-id|path> [...] [--depth N]"], False

    # Resolve each arg to seed node ids: exact node id, else all nodes in a path.
    seeds: list[str] = []
    unknown: list[str] = []
    for a in pos:
        if a in m.nodes:
            seeds.append(a)
            continue
        norm = a.lstrip("./")
        in_file = [nid for nid, n in m.nodes.items()
                   if n.get("path") and n["path"].lstrip("./") == norm]
        if in_file:
            seeds.extend(in_file)
        else:
            unknown.append(a)
    if not seeds:
        return [f"no graph node for: {', '.join(unknown)}"], False

    affect_kinds = ("calls", "imports", "contains", "invokes", "depends_on",
                    "references", "reads_config", "links")
    seen = {s: 0 for s in seeds}
    dq = deque((s, 0) for s in seeds)
    while dq:
        cur, d = dq.popleft()
        if depth_cap is not None and d >= depth_cap:
            continue
        for e in m.fanin(cur, affect_kinds):
            if e["src"] not in seen:
                seen[e["src"]] = d + 1
                dq.append((e["src"], d + 1))
    seedset = set(seeds)
    impacted = sorted((d, i) for i, d in seen.items() if i not in seedset)
    lines = [f"{d:3d}  {i}" for d, i in impacted]
    head = (f"impact of {len(seeds)} seed(s): {len(impacted)} dependents "
            f"(depth {depth_cap if depth_cap is not None else 'inf'})")
    if unknown:
        head += f" [unresolved: {', '.join(unknown)}]"
    return [head, *lines], True


QUERIES = {
    "fanin": q_fanin, "fanout": q_fanout, "coredeps": q_coredeps,
    "cycles": q_cycles, "dead": q_dead, "orphans": q_orphans,
    "dups": q_dups, "boundary": q_boundary, "path": q_path,
    "impact": q_impact,
}
