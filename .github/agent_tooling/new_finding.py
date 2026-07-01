#!/usr/bin/env python3
"""new_finding — stamp a findings file with the seed naming convention.

Usage: new_finding <agent> <slug> [--title "..."]
Path:  <FINDINGS_DIR>/<agent>_<YYYYMMDD>_<slug>.md   (FINDINGS_DIR from PROJECT.md §0)

Prints the created path. Exit 0 ok / 2 usage.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

SKELETON = """# {title}

Author: {agent} | Date: {date} | Status: draft

## Definition

`unknown:` what this proves, in falsifiable terms.

## Findings

| ID | Sev | Path | Fact | Action |
| --- | --- | --- | --- | --- |

## Evidence

- metric / probe / commit cited here. No vibes (C2).
"""


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    title = None
    for i, a in enumerate(argv):
        if a == "--title" and i + 1 < len(argv):
            title = argv[i + 1]
    args = [a for a in args if a != title] if title else args
    if len(args) < 2:
        lib.die("usage: new_finding <agent> <slug> [--title ...]")
    agent, slug = slugify(args[0]), slugify(args[1])
    date = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")

    fdir = lib.binding("FINDINGS_DIR", "docs/findings")
    root = lib.find_repo_root()
    out_dir = (root / fdir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{agent}_{date}_{slug}.md"
    if out.exists():
        lib.die(f"already exists: {lib.rel(out)}", 1)
    out.write_text(
        SKELETON.format(title=title or f"{agent}: {slug}", agent=agent, date=date),
        encoding="utf-8",
    )
    print(lib.rel(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
