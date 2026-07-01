#!/usr/bin/env python3
"""project — resolve a binding from PROJECT.md §0. The keystone tool.

Usage:
  project get <KEY>          print one binding value (exit 1 if unset)
  project all [--json]       print every binding
  project tier               print RIGOR_TIER (default 'standard')
  project gate               run the bound local gate (GATE_COMPILE then GATE_TEST)
  project path <KEY>        resolve a binding as a repo-relative path, assert exists
  project tools [--json]     list agent_tooling scripts + one-line job (from docstrings)
  project seed [--json]      readiness doctor: report unfilled bindings (exit 1 if any required unset)

Exit: 0 ok / 1 unset-or-missing / 2 usage.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def _get(key: str) -> str | None:
    return lib.binding(key)


def cmd_get(args: list[str]) -> int:
    if len(args) != 1:
        lib.die("usage: project get <KEY>")
    val = _get(args[0])
    if not lib.is_set(val):
        print("none")
        return 1
    print(val)
    return 0


def cmd_all(args: list[str]) -> int:
    b = lib.parse_bindings()
    lib.emit([f"{k} = {v}" for k, v in b.items()], "--json" in args, True,
             f"{len(b)} bindings")
    return 0


def cmd_tier(_: list[str]) -> int:
    print(_get("RIGOR_TIER") or "standard")
    return 0


def cmd_path(args: list[str]) -> int:
    if len(args) != 1:
        lib.die("usage: project path <KEY>")
    val = _get(args[0])
    if not lib.is_set(val):
        print(f"error: {args[0]} unset", file=sys.stderr)
        return 1
    p = (lib.find_repo_root() / val).resolve()
    print(p)
    return 0 if p.exists() else 1


def _first_doc(path: Path) -> str:
    """First job line of a tool: python docstring line, or sh header comment."""
    text = lib.read_text(path)
    if path.suffix == ".py":
        for marker in ('"""', "'''"):
            if marker in text:
                seg = text.split(marker, 2)
                if len(seg) >= 2 and seg[1].strip():
                    return seg[1].strip().splitlines()[0]
    else:  # sh: first non-shebang comment
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("#") and not s.startswith("#!"):
                return s.lstrip("# ")
    return "(no description)"


def cmd_tools(args: list[str]) -> int:
    here = Path(__file__).resolve().parent
    dirs = [here, here.parent / "graph_tooling", here.parent / "evals"]
    rows = []
    for d in dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix not in (".py", ".sh"):
                continue
            if "Usage:" not in lib.read_text(p):  # command marker; modules omit it
                continue
            rows.append({"tool": p.name, "job": _first_doc(p)})
    if "--json" in args:
        import json
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['tool']:<18}{r['job']}")
    return 0


def cmd_gate(_: list[str]) -> int:
    root = lib.find_repo_root()
    ran = 0
    for key in ("GATE_COMPILE", "GATE_TEST", "GATE_EXTRA"):
        cmd = _get(key)
        if not lib.is_set(cmd):
            continue
        ran += 1
        print(f"== {key}: {cmd}")
        rc = subprocess.run(cmd, shell=True, cwd=root).returncode
        if rc != 0:
            print(f"FAIL {key} exit {rc}")
            return 1
    if ran == 0:
        print("no gate commands bound (GATE_COMPILE/GATE_TEST unset)")
        return 1
    print(f"PASS gate ({ran} step(s))")
    return 0


# --- REQUIRED bindings an agent must fill before real work (PROJECT.md) ---
_REQUIRED = ("PROJECT_NAME", "PRIMARY_LANGS", "GATE_COMPILE", "GATE_TEST")
# Recommended but not blocking — flagged as advisory.
_RECOMMENDED = ("LIVE_TARGET", "CAPABILITY_LEDGER", "GOTCHA_LOG", "DEPLOY",
                "VERIFY", "CORE_FLOW_CHECK", "CONFIG_MODULE")


def cmd_seed(args: list[str]) -> int:
    """Readiness doctor: report unfilled bindings before real work begins.

    Exit 0 when every REQUIRED binding is set; 1 when any is unfilled. Advisory
    rows never fail the check. Points at the example manifests.
    """
    b = lib.parse_bindings()
    json_mode = "--json" in args

    def state(key: str) -> str:
        return "set" if lib.is_set(b.get(key)) else "UNSET"

    req = [(k, b.get(k, ""), state(k)) for k in _REQUIRED]
    rec = [(k, b.get(k, ""), state(k)) for k in _RECOMMENDED]
    missing = [k for k, _, s in req if s == "UNSET"]

    if json_mode:
        import json
        print(json.dumps({
            "ready": not missing,
            "required": [{"key": k, "value": v, "state": s} for k, v, s in req],
            "recommended": [{"key": k, "value": v, "state": s} for k, v, s in rec],
            "missing_required": missing,
        }, indent=2))
        return 0 if not missing else 1

    print("PROJECT.md readiness\n")
    print("REQUIRED (must set before real work):")
    for k, v, s in req:
        mark = "ok " if s == "set" else "!! "
        print(f"  {mark}{k:<18}{v or '(unset)'}")
    print("\nRECOMMENDED (advisory):")
    for k, v, s in rec:
        mark = "ok " if s == "set" else " . "
        print(f"  {mark}{k:<18}{v or '(unset)'}")
    print()
    if missing:
        print(f"FAIL not seeded: {len(missing)} required unset "
              f"({', '.join(missing)})")
        print("See .github/PROJECT.examples/ for filled manifests to copy.")
        return 1
    print("PASS seeded: all required bindings set")
    return 0


CMDS = {
    "get": cmd_get, "all": cmd_all, "tier": cmd_tier,
    "gate": cmd_gate, "path": cmd_path, "tools": cmd_tools,
    "seed": cmd_seed,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd not in CMDS:
        lib.die(f"unknown command '{cmd}'. one of: {', '.join(CMDS)}")
    return CMDS[cmd](rest)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
