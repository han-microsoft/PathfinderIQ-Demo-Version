"""Shared home for agent_tooling (C1). Bindings parse, repo walk, output.

Stdlib only. Every Python tool imports this. No logic duplicated across tools.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
IGNORE_SUFFIXES = {
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ico",
    ".woff", ".woff2", ".ttf", ".zip", ".gz", ".tar", ".pyc",
}


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up to the dir containing `.github`, else the git root, else cwd."""
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        if (d / ".github").is_dir() or (d / ".git").exists():
            return d
    return cur


def github_dir(root: Path | None = None) -> Path:
    root = root or find_repo_root()
    gh = root / ".github"
    return gh if gh.is_dir() else root


def project_md(root: Path | None = None) -> Path:
    return github_dir(root) / "PROJECT.md"


def parse_bindings(path: Path | None = None) -> dict[str, str]:
    """Parse the ```ini KEY = value ``` block under '## 0. Bindings' in PROJECT.md.

    Returns {} if file or block absent. `none` stays literal 'none' (caller decides).
    """
    path = path or project_md()
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_block = False
    seen_heading = False
    out: dict[str, str] = {}
    for line in text:
        if line.strip().startswith("## 0.") and "inding" in line:
            seen_heading = True
            continue
        if seen_heading and line.strip().startswith("```"):
            if not in_block:
                in_block = True
                continue
            break  # end of the first fenced block after the heading
        if in_block:
            raw = line.split("#", 1)[0].strip()
            if not raw or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def binding(key: str, default: str | None = None) -> str | None:
    val = parse_bindings().get(key)
    if val is None or val == "":
        return default
    return val


def is_set(val: str | None) -> bool:
    return bool(val) and val.lower() != "none"


def walk_files(root: Path, suffixes: tuple[str, ...] | None = None,
               exclude: tuple[str, ...] = ()):
    """Bounded recursive file walk honouring the ignore set.

    `exclude`: path substrings; any file whose repo-relative path contains one
    is skipped (visible scoping, never hidden — caller declares it).
    """
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in IGNORE_SUFFIXES:
                continue
            if suffixes and p.suffix.lower() not in suffixes:
                continue
            if exclude and any(x in str(p) for x in exclude):
                continue
            yield p


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return ""


def rel(p: Path, root: Path | None = None) -> str:
    root = root or find_repo_root()
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


# --- output ---------------------------------------------------------------

def emit(items, json_mode: bool, ok: bool, summary: str) -> None:
    if json_mode:
        print(json.dumps({"ok": ok, "summary": summary, "items": items}, indent=2))
    else:
        for it in items:
            print(it if isinstance(it, str) else json.dumps(it))
        print(("PASS " if ok else "FAIL ") + summary)


def die(msg: str, code: int = 2) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def parse_exclude(argv: list[str]) -> tuple[str, ...]:
    """Collect --exclude values (repeatable or comma-list) from argv."""
    out: list[str] = []
    for i, a in enumerate(argv):
        if a == "--exclude" and i + 1 < len(argv):
            out.extend(x for x in argv[i + 1].split(",") if x)
    return tuple(out)


def pos_args(argv: list[str], value_flags: tuple[str, ...] = ("--exclude",)) -> list[str]:
    """Positional args: drop --flags and the values consumed by value-taking flags.

    One home (C1) for the flag/positional split every tool needs.
    """
    skip = set()
    for i, a in enumerate(argv):
        if a in value_flags and i + 1 < len(argv):
            skip.add(i + 1)
    return [a for i, a in enumerate(argv)
            if not a.startswith("--") and i not in skip]
