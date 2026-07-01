#!/usr/bin/env python3
"""link_check — every markdown link + referenced relative path resolves (T5).

Catches doc-drift: a link to a moved/deleted file = a doc that lies.

Usage: link_check [ROOT] [--json] [--exclude SUBSTR[,SUBSTR]]
Exit: 0 all resolve / 1 broken links found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

LINK = re.compile(r"\[(?:[^\]]*)\]\(([^)]+)\)")


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#", "tel:"))


def check_file(md: Path) -> list[dict]:
    broken = []
    text = lib.read_text(md)
    for n, line in enumerate(text.splitlines(), 1):
        for m in LINK.finditer(line):
            target = m.group(1).split()[0].strip()  # drop optional "title"
            if is_external(target):
                continue
            path_part = target.split("#", 1)[0]
            if not path_part:
                continue
            resolved = (md.parent / path_part).resolve()
            if not resolved.exists():
                broken.append({"file": lib.rel(md), "line": n, "target": target})
    return broken


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    exclude = lib.parse_exclude(argv)
    pos = lib.pos_args(argv)
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()
    broken: list[dict] = []
    scanned = 0
    for md in lib.walk_files(root, suffixes=(".md",), exclude=exclude):
        scanned += 1
        broken.extend(check_file(md))
    ok = not broken
    items = [f"{b['file']}:{b['line']} -> {b['target']}" for b in broken] if not json_mode else broken
    lib.emit(items, json_mode, ok, f"{scanned} md scanned, {len(broken)} broken")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
