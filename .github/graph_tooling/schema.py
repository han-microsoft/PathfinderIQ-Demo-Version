"""graph_tooling schema (C1). Vocab, version, spine validator. One home.

Stdlib only. Every graph tool imports this. No vocab duplicated elsewhere.
"""
from __future__ import annotations

SCHEMA_VERSION = 1

LANGS = {"python", "markdown", "shell", "data", "none"}

NODE_KINDS = {
    "file", "module", "package", "function", "method", "class",
    "doc", "heading", "script", "data_asset", "config_key", "external",
}

EDGE_KINDS = {
    "contains", "imports", "calls", "defines", "references", "links",
    "invokes", "reads_config", "depends_on", "declared_dep", "declared_leaf",
}

BANDS = {"derived", "declared"}

NODE_SPINE = ("id", "kind", "lang", "path", "span", "name", "band", "source", "attrs")
EDGE_SPINE = ("id", "kind", "src", "dst", "band", "source", "attrs")


def validate_node(rec: dict) -> list[str]:
    errs: list[str] = []
    for f in NODE_SPINE:
        if f not in rec:
            errs.append(f"node missing field '{f}': {rec.get('id', '?')}")
    if errs:
        return errs
    if rec["kind"] not in NODE_KINDS:
        errs.append(f"node bad kind '{rec['kind']}': {rec['id']}")
    if rec["lang"] not in LANGS:
        errs.append(f"node bad lang '{rec['lang']}': {rec['id']}")
    if rec["band"] not in BANDS:
        errs.append(f"node bad band '{rec['band']}': {rec['id']}")
    if rec["span"] is not None and (
        not isinstance(rec["span"], (list, tuple)) or len(rec["span"]) != 2
    ):
        errs.append(f"node bad span: {rec['id']}")
    if not isinstance(rec["attrs"], dict):
        errs.append(f"node attrs not object: {rec['id']}")
    return errs


def validate_edge(rec: dict) -> list[str]:
    errs: list[str] = []
    for f in EDGE_SPINE:
        if f not in rec:
            errs.append(f"edge missing field '{f}': {rec.get('id', '?')}")
    if errs:
        return errs
    if rec["kind"] not in EDGE_KINDS:
        errs.append(f"edge bad kind '{rec['kind']}': {rec['id']}")
    if rec["band"] not in BANDS:
        errs.append(f"edge bad band '{rec['band']}': {rec['id']}")
    if not isinstance(rec["attrs"], dict):
        errs.append(f"edge attrs not object: {rec['id']}")
    return errs
