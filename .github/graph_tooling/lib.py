"""graph_tooling shared home (C1). Graph IO, id grammar, record merge, manifest.

Stdlib only. Reuses agent_tooling/lib.py for bindings parse + bounded walk +
repo root. No duplication of those primitives.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import schema

# reuse agent_tooling primitives (C1). Load by path under a distinct module
# name to avoid colliding with this module (both files are named lib.py).
_atl_path = Path(__file__).resolve().parent.parent / "agent_tooling" / "lib.py"
_spec = importlib.util.spec_from_file_location("agent_tooling_lib", _atl_path)
atl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atl)

find_repo_root = atl.find_repo_root
github_dir = atl.github_dir
walk_files = atl.walk_files
read_text = atl.read_text
rel = atl.rel
binding = atl.binding
is_set = atl.is_set
die = atl.die


def graph_dir(root: Path | None = None) -> Path:
    """Snapshot lives in <repo>/graph/ (project data, regenerated on build)."""
    root = root or find_repo_root()
    return root / "graph"


# --- id grammar -----------------------------------------------------------

def nid(lang: str, kind: str, path: str, qual: str | None = None) -> str:
    """Build a deterministic, structured node id. No line number (P4 stability)."""
    base = f"{lang}:{kind}:{path}"
    return f"{base}#{qual}" if qual else base


def eid(kind: str, src: str, dst: str) -> str:
    """Build a deterministic edge id from kind + endpoint ids."""
    return f"{kind}:{src}->{dst}"


def parse_nid(node_id: str) -> dict:
    """Parse a node id back into parts. Queries filter without a side table."""
    qual = None
    body = node_id
    if "#" in node_id:
        body, qual = node_id.split("#", 1)
    parts = body.split(":", 2)
    if len(parts) != 3:
        return {"lang": None, "kind": None, "path": body, "qual": qual}
    return {"lang": parts[0], "kind": parts[1], "path": parts[2], "qual": qual}


# --- record constructors --------------------------------------------------

def node(id_: str, kind: str, lang: str, path: str, name: str,
         span=None, band: str = "derived", source: str = "?",
         attrs: dict | None = None) -> dict:
    return {
        "id": id_, "kind": kind, "lang": lang, "path": path,
        "span": list(span) if span else None, "name": name,
        "band": band, "source": source, "attrs": attrs or {},
    }


def edge(kind: str, src: str, dst: str, band: str = "derived",
         source: str = "?", attrs: dict | None = None) -> dict:
    return {
        "id": eid(kind, src, dst), "kind": kind, "src": src, "dst": dst,
        "band": band, "source": source, "attrs": attrs or {},
    }


# --- jsonl IO (deterministic: sorted by id, sorted keys) ------------------

def dump_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(records, key=lambda r: r["id"])
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln:
            out.append(json.loads(ln))
    return out


def dump_worklist(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(items, key=lambda r: (r["caller_id"], r["line"]))
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


# --- merge: derived first, overlay enriches by id (attrs win) -------------

def merge_overlay(derived: list[dict], overlay: list[dict]) -> tuple[list[dict], list[str]]:
    """Merge declared overlay into derived. Returns (merged, collision_log).

    Overlay record id-matches a derived record -> attrs merged, overlay wins on
    key collision (logged). Else introduced as a pure-declared record.
    """
    by_id = {r["id"]: r for r in derived}
    collisions: list[str] = []
    for ov in overlay:
        tgt = by_id.get(ov["id"])
        if tgt is None:
            by_id[ov["id"]] = ov  # pure-declared
            continue
        for k, v in ov.get("attrs", {}).items():
            if k in tgt["attrs"] and tgt["attrs"][k] != v:
                collisions.append(f"{ov['id']}#{k}")
            tgt["attrs"][k] = v
    return list(by_id.values()), collisions


# --- manifest -------------------------------------------------------------

def write_manifest(gdir: Path, counts: dict, coverage: dict,
                   collisions: list[str]) -> None:
    man = {
        "schema_version": schema.SCHEMA_VERSION,
        "counts": counts,
        "coverage": coverage,
        "merge_collisions": sorted(collisions),
    }
    (gdir / "manifest.json").write_text(
        json.dumps(man, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_manifest(gdir: Path) -> dict:
    p = gdir / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


class ExtractResult:
    """Standard extractor return (C1). records + worklist + coverage."""

    def __init__(self):
        self.records: list[dict] = []
        self.worklist: list[dict] = []
        self.coverage: dict = {}
