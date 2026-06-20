"""extract_md — Markdown nodes + edges. stdlib regex.

Emits: doc + heading nodes; contains + links edges. In-repo link target ->
node id; external/URL link -> ext node. Declares coverage.
"""
from __future__ import annotations

import re
from pathlib import Path

import lib as G

CLAIM_SUFFIXES = (".md",)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ExtractResult = G.ExtractResult


def claims(path: Path) -> bool:
    return path.suffix.lower() in CLAIM_SUFFIXES


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", s).strip("-")


def extract(root: Path, paths: list[str]) -> ExtractResult:
    res = ExtractResult()
    files = [Path(p) for p in paths if p.endswith(".md")]
    ext_seen: set[str] = set()
    links_total = 0
    links_internal = 0

    def ext_node(target: str) -> str:
        nidv = f"ext:url:{target}"
        if target not in ext_seen:
            ext_seen.add(target)
            res.records.append(G.node(nidv, "external", "none", "", target,
                                      source="extract_md"))
        return nidv

    for f in files:
        rp = G.rel(f, root)
        did = G.nid("markdown", "doc", rp)
        res.records.append(G.node(did, "doc", "markdown", rp, Path(rp).name,
                                  source="extract_md"))
        text = G.read_text(f)
        in_fence = False
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = _HEADING.match(line)
            if m:
                title = m.group(2).strip()
                hid = G.nid("markdown", "heading", rp, _slug(title))
                res.records.append(G.node(
                    hid, "heading", "markdown", rp, title, span=(i, i),
                    source="extract_md"))
                res.records.append(G.edge("contains", did, hid,
                                          source="extract_md"))
            for lm in _LINK.finditer(line):
                target = lm.group(1).strip()
                links_total += 1
                if target.startswith(("http://", "https://", "mailto:")):
                    res.records.append(G.edge("links", did, ext_node(target),
                                              source="extract_md"))
                    continue
                # in-repo relative link
                frag = target.split("#", 1)[0]
                if not frag:
                    continue
                tgt_path = (f.parent / frag).resolve()
                if tgt_path.is_file():
                    trp = G.rel(tgt_path, root)
                    tid = (G.nid("markdown", "doc", trp) if trp.endswith(".md")
                           else f"file:{trp}")
                    res.records.append(G.edge("links", did, tid,
                                              source="extract_md",
                                              attrs={"raw": target}))
                    links_internal += 1
                else:
                    res.records.append(G.edge("links", did, ext_node(target),
                                              source="extract_md",
                                              attrs={"broken": True}))

    res.coverage = {
        "md_files": len(files),
        "md_links_total": links_total,
        "md_links_internal": links_internal,
    }
    return res
