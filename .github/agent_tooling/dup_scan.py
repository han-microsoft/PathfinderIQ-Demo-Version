#!/usr/bin/env python3
"""dup_scan — duplicated code/text blocks (P1).

Normalized sliding-window hash. Reports spans of >= N identical (whitespace-
normalized) non-trivial lines appearing in >1 place. Catches copy-paste that
should flow from one source.

Usage: dup_scan [ROOT] [--window N] [--ext .py,.ts,.md] [--json]
  --window : min block size in lines (default 6)
  --ext    : comma list of suffixes to scan (default: code-ish)
Exit: 0 no dup / 1 duplicate blocks found.
"""
from __future__ import annotations

import hashlib
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

DEFAULT_EXT = (".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".go", ".rs", ".java")

BOILERPLATE = (
    "import ", "from ", "sys.path", "#!", '"""', "'''", "if __name__",
    "raise SystemExit", "export ", "const ", "require(", "package ", "use ",
    "#include", "//", "# ", "from __future__",
)


def norm(line: str) -> str:
    return " ".join(line.split())


def is_boilerplate(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith(BOILERPLATE)


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv

    def opt(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    window = int(opt("--window", "6"))
    ext_arg = opt("--ext", "")
    exts = tuple(e if e.startswith(".") else "." + e
                 for e in ext_arg.split(",")) if ext_arg else DEFAULT_EXT
    pos = [a for a in argv if not a.startswith("--")
           and a not in (ext_arg, str(window)) ]
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()

    # hash -> list of (file, start_line)
    table: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for f in lib.walk_files(root, suffixes=exts):
        lines = [norm(l) for l in lib.read_text(f).splitlines()]
        # skip windows that are mostly trivial (blank/braces)
        for i in range(len(lines) - window + 1):
            block = lines[i:i + window]
            meaningful = [b for b in block if len(b) > 3]
            if len(meaningful) < window - 1:
                continue
            # skip import/bootstrap preamble: P1 is logic dup, not import boilerplate
            if sum(1 for b in block if is_boilerplate(b)) > window // 2:
                continue
            h = hashlib.sha1("\n".join(block).encode()).hexdigest()
            table[h].append((lib.rel(f), i + 1))

    dups = {h: locs for h, locs in table.items() if len(locs) > 1}
    items = []
    for h, locs in sorted(dups.items(), key=lambda kv: -len(kv[1])):
        where = "; ".join(f"{f}:{ln}" for f, ln in locs)
        items.append({"hash": h[:8], "count": len(locs), "locs": where}
                     if json_mode else f"x{len(locs)} [{window}L] {where}")
    ok = not dups
    lib.emit(items, json_mode, ok, f"{len(dups)} duplicated block group(s), window={window}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
