#!/usr/bin/env python3
"""secret_scan — hardcoded creds/keys/tokens/connection-strings (safety gate).

Pattern set + high-entropy heuristic. Read-only; reports candidates for human
triage. False positives expected — this is a tripwire, not a vault.

Usage: secret_scan [ROOT] [--json]
Exit: 0 none / 1 candidate secrets found.
Skips this tool's own pattern definitions and obvious placeholders.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

PATTERNS = [
    ("aws_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("conn_string", re.compile(r"(?:AccountKey|Password|Pwd)\s*=\s*[^;\s\"']{6,}", re.I)),
    ("bearer", re.compile(r"\b(?:Bearer|token|api[_-]?key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{20,}", re.I)),
    ("slack", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("generic_secret", re.compile(r"(?:secret|passwd|password)\s*[:=]\s*['\"][^'\"]{6,}['\"]", re.I)),
]
PLACEHOLDER = re.compile(
    r"(TODO|EXAMPLE|PLACEHOLDER|CHANGEME|xxx+|<[^>]+>|\benv\b|\$\{|os\.getenv|process\.env|None|none)",
    re.I,
)
SECRETISH_ASSIGN = re.compile(
    r"(?:secret|token|key|passwd|password|apikey)\s*[:=]\s*['\"]([A-Za-z0-9_\-+/]{20,})['\"]",
    re.I,
)


def entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {c: s.count(c) for c in set(s)}
    return -sum((n / len(s)) * math.log2(n / len(s)) for n in freq.values())


def main(argv: list[str]) -> int:
    json_mode = "--json" in argv
    pos = [a for a in argv if not a.startswith("--")]
    root = Path(pos[0]).resolve() if pos else lib.find_repo_root()
    self_path = Path(__file__).resolve()

    hits: list[dict] = []
    for f in lib.walk_files(root):
        if f.resolve() == self_path:  # skip own pattern defs
            continue
        if f.suffix.lower() not in (
            ".py", ".ts", ".tsx", ".js", ".jsx", ".sh", ".env", ".json",
            ".yaml", ".yml", ".toml", ".ini", ".cfg", ".go", ".rs", ".java", ".md",
        ):
            continue
        for n, line in enumerate(lib.read_text(f).splitlines(), 1):
            if len(line) > 500:
                continue
            for name, pat in PATTERNS:
                if pat.search(line) and not PLACEHOLDER.search(line):
                    hits.append({"file": lib.rel(f), "line": n, "kind": name})
            m = SECRETISH_ASSIGN.search(line)
            if m and not PLACEHOLDER.search(line) and entropy(m.group(1)) >= 3.5:
                hits.append({"file": lib.rel(f), "line": n, "kind": "high_entropy_secret"})

    # dedupe
    seen = set()
    uniq = []
    for h in hits:
        k = (h["file"], h["line"], h["kind"])
        if k not in seen:
            seen.add(k)
            uniq.append(h)

    items = ([f"{h['file']}:{h['line']} {h['kind']}" for h in uniq]
             if not json_mode else uniq)
    ok = not uniq
    lib.emit(items, json_mode, ok, f"{len(uniq)} secret candidate(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
