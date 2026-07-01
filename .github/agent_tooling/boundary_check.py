#!/usr/bin/env python3
"""boundary_check — env reads outside the config module (config boundary §6).

If PROJECT.md binds CONFIG_MODULE, every os.getenv / os.environ / process.env
read must live inside it. Reads elsewhere leak config across the boundary.

Usage: boundary_check [ROOT] [--json]
Exit:
  0  no violation (or CONFIG_MODULE unset -> skipped, exit 0 with note)
  1  env read outside the config module
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

ENV_READ = re.compile(r"os\.getenv|os\.environ|process\.env|import\s+os\b")
ENV_STRICT = re.compile(r"os\.getenv|os\.environ\b|process\.env")


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    pos = [a for a in argv if not a.startswith("--")]
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()

    cfg = lib.binding("CONFIG_MODULE")
    if not lib.is_set(cfg):
        lib.emit([], json_mode, True, "CONFIG_MODULE unset — boundary not enforced")
        return 0
    allowed = {c.strip() for c in cfg.split(",") if c.strip()}

    def in_config(relpath: str) -> bool:
        return any(a in relpath or relpath.endswith(a) for a in allowed)

    violations: list[dict] = []
    for f in lib.walk_files(root, suffixes=(".py", ".ts", ".tsx", ".js", ".jsx")):
        relp = lib.rel(f)
        if in_config(relp):
            continue
        for n, line in enumerate(lib.read_text(f).splitlines(), 1):
            if ENV_STRICT.search(line):
                violations.append({"file": relp, "line": n,
                                   "text": line.strip()[:80]})

    items = ([f"{v['file']}:{v['line']} {v['text']}" for v in violations]
             if not json_mode else violations)
    ok = not violations
    lib.emit(items, json_mode, ok,
             f"config={','.join(allowed)}; {len(violations)} leak(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
