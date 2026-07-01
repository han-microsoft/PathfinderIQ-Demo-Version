"""extract_py — Python nodes + edges. AST only, stdlib.

Emits: module/function/method/class nodes; contains/imports/defines/depends_on/
references edges; calls via tagger -> resolver -> worklist. Declares coverage.
assumes: Python source. Skips syntactically-invalid files (reported in coverage).
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

import lib as G


CLAIM_SUFFIXES = (".py",)
ExtractResult = G.ExtractResult
_BUILTINS = frozenset(dir(builtins))


def claims(path: Path) -> bool:
    return path.suffix.lower() in CLAIM_SUFFIXES


def _dotted(relpath: str) -> str:
    p = relpath[:-3] if relpath.endswith(".py") else relpath
    p = p[:-9] if p.endswith("/__init__") else p
    return p.replace("/", ".")


def _qual(stack: list[str], name: str) -> str:
    return ".".join([*stack, name]) if stack else name


def extract(root: Path, paths: list[str]) -> ExtractResult:
    res = ExtractResult()
    files = [Path(p) for p in paths if p.endswith(".py")]

    # --- pass 1: parse, collect modules + defs (cross-module index) -------
    parsed: dict[str, ast.Module] = {}
    bad = 0
    mod_node: dict[str, str] = {}           # relpath -> module node id
    by_dotted: dict[str, str] = {}          # dotted -> module node id
    by_base: dict[str, list[str]] = {}      # last segment -> [module node id]
    local_defs: dict[str, dict[str, str]] = {}   # relpath -> {simple name: node id}
    name_index: dict[str, list[str]] = {}        # simple name -> [def node ids]

    for f in files:
        rp = G.rel(f, root)
        src = G.read_text(f)
        try:
            tree = ast.parse(src, filename=rp)
        except SyntaxError:
            bad += 1
            continue
        parsed[rp] = tree
        mid = G.nid("python", "module", rp)
        mod_node[rp] = mid
        dotted = _dotted(rp)
        by_dotted[dotted] = mid
        by_base.setdefault(dotted.split(".")[-1], []).append(mid)
        local_defs[rp] = {}

    def resolve_module(dotted: str, from_dir: str | None = None) -> str | None:
        if dotted in by_dotted:
            return by_dotted[dotted]
        base = dotted.split(".")[-1]
        hits = by_base.get(base, [])
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1 and from_dir is not None:
            # flat-layout disambiguation: prefer a sibling in the importer's dir
            same = [h for h in hits
                    if str(Path(G.parse_nid(h)["path"]).parent) == from_dir]
            if len(same) == 1:
                return same[0]
        return None

    # collect defs + nodes
    for rp, tree in parsed.items():
        mid = mod_node[rp]
        res.records.append(G.node(
            mid, "module", "python", rp, _dotted(rp).split(".")[-1],
            band="derived", source="extract_py"))

        def visit_body(body, stack, parent_id):
            for n in body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "method" if stack else "function"
                elif isinstance(n, ast.ClassDef):
                    kind = "class"
                else:
                    continue
                qual = _qual(stack, n.name)
                nidv = G.nid("python", kind, rp, qual)
                res.records.append(G.node(
                    nidv, kind, "python", rp, n.name,
                    span=(n.lineno, getattr(n, "end_lineno", n.lineno)),
                    source="extract_py"))
                res.records.append(G.edge("contains", parent_id, nidv,
                                          source="extract_py"))
                local_defs[rp][n.name] = nidv
                name_index.setdefault(n.name, []).append(nidv)
                visit_body(n.body, [*stack, n.name], nidv)

        visit_body(tree.body, [], mid)

    # --- pass 2: imports + calls -----------------------------------------
    ext_seen: set[str] = set()
    calls_total = 0
    calls_project = 0
    calls_external = 0

    def ext(cat: str, name: str) -> str:
        """One home for external node minting: ext:<cat>:<name> (pkg/builtin/method)."""
        nidv = f"ext:{cat}:{name}"
        if nidv not in ext_seen:
            ext_seen.add(nidv)
            res.records.append(G.node(
                nidv, "external", "none", "", name, band="derived",
                source="extract_py"))
        return nidv

    def ext_pkg(dotted: str) -> str:
        return ext("pkg", dotted.split(".")[0])

    def ext_builtin(name: str) -> str:
        return ext("builtin", name)

    def ext_method(name: str) -> str:
        return ext("method", name)

    for rp, tree in parsed.items():
        mid = mod_node[rp]
        from_dir = str(Path(rp).parent)
        # import table: local name -> ('mod', dotted) | ('sym', dotted, symbol)
        imports: dict[str, tuple] = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    local = a.asname or a.name.split(".")[0]
                    imports[local] = ("mod", a.name)
                    tgt = resolve_module(a.name, from_dir)
                    if tgt:
                        res.records.append(G.edge("imports", mid, tgt,
                                                  source="extract_py"))
                    else:
                        res.records.append(G.edge("depends_on", mid, ext_pkg(a.name),
                                                  source="extract_py"))
            elif isinstance(n, ast.ImportFrom):
                if n.level and not n.module:
                    continue
                base = n.module or ""
                for a in n.names:
                    local = a.asname or a.name
                    imports[local] = ("sym", base, a.name)
                tgt = resolve_module(base, from_dir)
                if tgt:
                    res.records.append(G.edge("imports", mid, tgt,
                                              source="extract_py"))
                elif base:
                    res.records.append(G.edge("depends_on", mid, ext_pkg(base),
                                              source="extract_py"))

        # map a line -> enclosing def node id (caller resolution)
        caller_at: dict[int, str] = {}

        def map_callers(body, stack, owner):
            for n in body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    qual = _qual(stack, n.name)
                    kind = ("class" if isinstance(n, ast.ClassDef)
                            else "method" if stack else "function")
                    own = G.nid("python", kind, rp, qual)
                    lo, hi = n.lineno, getattr(n, "end_lineno", n.lineno)
                    if not isinstance(n, ast.ClassDef):
                        for ln in range(lo, hi + 1):
                            caller_at[ln] = own
                    map_callers(n.body, [*stack, n.name], own)

        map_callers(tree.body, [], mid)

        def caller_of(line: int) -> str:
            return caller_at.get(line, mid)

        # tagger + resolver
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            calls_total += 1
            caller = caller_of(getattr(n, "lineno", 0))
            fn = n.func
            callee = None
            base = None
            if isinstance(fn, ast.Name):
                callee = fn.id
            elif isinstance(fn, ast.Attribute):
                callee = fn.attr
                if isinstance(fn.value, ast.Name):
                    base = fn.value.id
            if callee is None:
                res.worklist.append(_wl(caller, "<dynamic>", n.lineno,
                                        _arity(n), "dynamic"))
                continue

            dst, conf, resolver, cand = _resolve(
                callee, base, rp, imports, local_defs, name_index,
                resolve_module, ext_pkg, from_dir, ext_builtin)
            if dst is None:
                # _resolve returns None only when the callee binds to no project
                # def, builtin, or import. If the name matches a project def it is
                # a genuine candidate an agent should resolve -> worklist. Else it
                # is provably a library/instance method (str.lower, Path.resolve,
                # list.append) with no project node -> resolved-external edge, not
                # an agent task. Keeps the worklist a real queue, metric honest.
                if callee in name_index:
                    res.worklist.append(_wl(caller, callee, n.lineno,
                                            _arity(n), conf))
                    continue
                dst, conf, resolver = ext_method(callee), "high", "external"
            if dst.startswith("ext:"):
                calls_external += 1
            else:
                calls_project += 1
            attrs = {"confidence": conf, "resolver": resolver, "line": n.lineno}
            if cand:
                attrs["candidates"] = cand
            res.records.append(G.edge("calls", caller, dst,
                                      source="extract_py", attrs=attrs))

    res.coverage = {
        "py_files": len(files),
        "py_parsed": len(parsed),
        "py_syntax_errors": bad,
        "calls_total": calls_total,
        "calls_resolved": calls_project + calls_external,
        "calls_project": calls_project,
        "calls_external": calls_external,
        "calls_worklist": len(res.worklist),
    }
    return res


def _arity(call: ast.Call) -> int:
    return len(call.args) + len(call.keywords)


def _wl(caller: str, callee: str, line: int, arity: int, reason: str) -> dict:
    return {"caller_id": caller, "callee_name": callee, "line": line,
            "arity": arity, "reason": reason, "status": "open"}


def _resolve(callee, base, rp, imports, local_defs, name_index,
             resolve_module, ext_pkg, from_dir=None, ext_builtin=None):
    """Return (dst_id|None, confidence_or_reason, resolver, candidates|None)."""
    # attribute call on imported module alias: base.callee
    if base is not None:
        imp = imports.get(base)
        if imp and imp[0] == "mod":
            tgt = resolve_module(imp[1], from_dir)
            if tgt:
                pr = G.parse_nid(tgt)
                dst = G.nid("python", "function", pr["path"], callee)
                return dst, "high", "static", None
            return ext_pkg(imp[1]), "high", "static", None
        return None, "dynamic", "static", None
    # bare name: local def first
    if callee in local_defs.get(rp, {}):
        return local_defs[rp][callee], "high", "static", None
    # imported symbol
    imp = imports.get(callee)
    if imp and imp[0] == "sym":
        tgt = resolve_module(imp[1], from_dir)
        if tgt:
            pr = G.parse_nid(tgt)
            dst = G.nid("python", "function", pr["path"], imp[2])
            return dst, "high", "static", None
        if imp[1]:
            return ext_pkg(imp[1]), "high", "static", None
    if imp and imp[0] == "mod":
        return ext_pkg(imp[1]), "high", "static", None
    # python builtin (LEGB: after local + imported globals, before fuzzy index)
    if callee in _BUILTINS and ext_builtin is not None:
        return ext_builtin(callee), "high", "static", None
    # global index fallback
    hits = name_index.get(callee, [])
    if len(hits) == 1:
        return hits[0], "low", "static", None
    if len(hits) > 1:
        return hits[0], "low", "static", hits[:5]
    return None, "unknown", "static", None
