"""extract_data — data_asset nodes from PROJECT.md-bound globs. No derived edges.

Flows between data assets and code are declared band (graph declare). This
extractor only registers the asset nodes. Coverage = count. Binding key:
GRAPH_DATA_GLOBS (comma list of globs, relative to repo root); unset -> skip.
"""
from __future__ import annotations

from pathlib import Path

import lib as G

CLAIM_SUFFIXES: tuple = ()
ExtractResult = G.ExtractResult


def claims(path: Path) -> bool:
    return False  # glob-driven, not extension-driven


def extract(root: Path, paths: list[str]) -> ExtractResult:
    res = ExtractResult()
    globs = G.binding("GRAPH_DATA_GLOBS")
    if not G.is_set(globs):
        res.coverage = {"data_assets": 0, "data_globs": "unset"}
        return res
    seen: set[str] = set()
    for pat in [g.strip() for g in globs.split(",") if g.strip()]:
        for f in root.glob(pat):
            if not f.is_file():
                continue
            rp = G.rel(f, root)
            if rp in seen:
                continue
            seen.add(rp)
            res.records.append(G.node(
                f"data:asset:{rp}", "data_asset", "data", rp, Path(rp).name,
                source="extract_data"))
    res.coverage = {"data_assets": len(seen), "data_globs": globs}
    return res
