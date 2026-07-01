#!/usr/bin/env python3
"""module_size — LOC census; flag god-module candidates (P5).

Big module = low signal-per-token + high decay. Flags files over a threshold as
remodel candidates. Counts non-blank, non-comment-only lines.

Usage: module_size [ROOT] [--max N] [--ext .py,.ts] [--json]
  --max : flag threshold (default 600)
Exit: 0 none over / 1 one or more over the threshold.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

DEFAULT_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".go", ".rs", ".java", ".md")
COMMENT_PREFIX = ("#", "//", "*", "/*", "<!--")


def loc(text: str) -> int:
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(COMMENT_PREFIX):
            continue
        n += 1
    return n


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv

    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    maxn = int(opt("--max", "600"))
    ext_arg = opt("--ext", "")
    exts = tuple(e if e.startswith(".") else "." + e
                 for e in ext_arg.split(",")) if ext_arg else DEFAULT_EXT
    pos = [a for a in argv if not a.startswith("--") and a != ext_arg and a != str(maxn)]
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()

    rows = []
    for f in lib.walk_files(root, suffixes=exts):
        n = loc(lib.read_text(f))
        rows.append((n, lib.rel(f)))
    rows.sort(reverse=True)
    over = [(n, f) for n, f in rows if n > maxn]

    items = ([{"loc": n, "file": f} for n, f in over] if json_mode
             else [f"{n:>6}  {f}" for n, f in over])
    ok = not over
    biggest = rows[0] if rows else (0, "-")
    lib.emit(items, json_mode, ok,
             f"{len(over)} over {maxn} LOC; biggest {biggest[1]} ({biggest[0]})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
