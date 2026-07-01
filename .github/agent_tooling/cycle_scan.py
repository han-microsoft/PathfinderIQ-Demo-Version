#!/usr/bin/env python3
"""cycle_scan — import-cycle detector (P1 DAG). Python only.

Builds the intra-repo import graph and reports strongly-connected components
larger than one node = import cycles. `assumes:` Python; other langs need their
own resolver (reports skip count).

Usage: cycle_scan [ROOT] [--json]
Exit: 0 acyclic / 1 cycle(s) found.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def module_name(path: Path, root: Path) -> str:
    rel = path.resolve().relative_to(root.resolve()).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    pos = [a for a in argv if not a.startswith("--")]
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()

    py = list(lib.walk_files(root, suffixes=(".py",)))
    mods = {module_name(p, root): p for p in py}
    graph: dict[str, set[str]] = {m: set() for m in mods}

    for mod, path in mods.items():
        try:
            tree = ast.parse(lib.read_text(path))
        except SyntaxError:
            continue
        pkg = mod.rsplit(".", 1)[0] if "." in mod else ""
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level and pkg:  # relative import
                    base = pkg.rsplit(".", node.level - 1)[0] if node.level > 1 else pkg
                    targets = [f"{base}.{node.module}" if node.module else base]
                elif node.module:
                    targets = [node.module]
            for t in targets:
                # match to a known repo module (longest prefix)
                for cand in mods:
                    if t == cand or t.startswith(cand + ".") or cand.endswith("." + t):
                        if cand != mod:
                            graph[mod].add(cand)

    # Tarjan SCC
    index = {}
    low = {}
    onstack = set()
    stack: list[str] = []
    counter = [0]
    sccs: list[list[str]] = []

    sys.setrecursionlimit(10000)

    def strongconnect(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in graph:
        if v not in index:
            strongconnect(v)

    cycles = [c for c in sccs if len(c) > 1]
    # self-loop modules (import self) — rare, flag too
    self_loops = [m for m in graph if m in graph[m]]

    items = []
    for c in cycles:
        items.append({"cycle": c} if json_mode else "cycle: " + " -> ".join(c))
    for m in self_loops:
        items.append({"self": m} if json_mode else f"self-import: {m}")
    ok = not cycles and not self_loops
    lib.emit(items, json_mode, ok,
             f"{len(mods)} py modules, {len(cycles)} cycle(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
