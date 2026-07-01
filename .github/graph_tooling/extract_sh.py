"""extract_sh — Shell script nodes + invokes edges. stdlib regex, best-effort.

Emits: script nodes (.sh + shebang scripts); invokes edges (script -> in-repo
script, else external binary). assumes: POSIX-ish. Declares coverage.
"""
from __future__ import annotations

import re
from pathlib import Path

import lib as G

CLAIM_SUFFIXES = (".sh",)
_TOKEN = re.compile(r"(?:^|[|&;(]|\$\()\s*([\w./-]+)")
ExtractResult = G.ExtractResult


def claims(path: Path) -> bool:
    if path.suffix.lower() in CLAIM_SUFFIXES:
        return True
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
        return first.startswith("#!") and "sh" in first
    except OSError:
        return False


def extract(root: Path, paths: list[str]) -> ExtractResult:
    res = ExtractResult()
    files = [Path(p) for p in paths]
    files = [f for f in files if claims(f)]
    scripts = {G.rel(f, root): f for f in files}
    by_base = {Path(rp).name: G.nid("shell", "script", rp) for rp in scripts}
    ext_seen: set[str] = set()
    invokes = 0

    def ext_bin(name: str) -> str:
        nidv = f"ext:bin:{name}"
        if name not in ext_seen:
            ext_seen.add(name)
            res.records.append(G.node(nidv, "external", "none", "", name,
                                      source="extract_sh"))
        return nidv

    for rp, f in scripts.items():
        sid = G.nid("shell", "script", rp)
        res.records.append(G.node(sid, "script", "shell", rp, Path(rp).name,
                                  source="extract_sh"))
        text = G.read_text(f)
        seen_edge: set[str] = set()
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            for m in _TOKEN.finditer(line):
                tok = m.group(1)
                cmd = Path(tok).name
                if cmd in ("if", "then", "else", "fi", "for", "do", "done",
                           "while", "case", "esac", "echo", "cd", "true",
                           "false", "set", "local", "return", "exit"):
                    continue
                invokes += 1
                if cmd in by_base and by_base[cmd] != sid:
                    dst = by_base[cmd]
                else:
                    dst = ext_bin(cmd)
                key = dst
                if key in seen_edge:
                    continue
                seen_edge.add(key)
                res.records.append(G.edge("invokes", sid, dst,
                                          source="extract_sh"))

    res.coverage = {"sh_files": len(scripts), "sh_invokes": invokes}
    return res
