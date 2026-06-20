#!/usr/bin/env python3
"""run_all — run every read-only audit, one digest table, aggregate exit.

Not a god-script: only dispatches the other tools. Exit 1 if any audit fails.

Usage: run_all [ROOT] [--json]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

HERE = Path(__file__).resolve().parent
GRAPH = HERE.parent / "graph_tooling" / "graph.py"
AUDITS = [
    ("link_check", "link_check.py"),
    ("bloat_lint", "bloat_lint.py"),
    ("dup_scan", "dup_scan.py"),
    ("module_size", "module_size.py"),
    ("cycle_scan", "cycle_scan.py"),
    ("secret_scan", "secret_scan.py"),
    ("boundary_check", "boundary_check.py"),
]


def _run(name: str, cmd: list[str]) -> tuple[str, str, int]:
    """Run one audit subprocess; return (verdict, summary, rc)."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    rc = proc.returncode
    summary = ""
    for line in proc.stdout.splitlines():
        if line.startswith(("PASS ", "FAIL ")):
            summary = line
    return ("PASS" if rc == 0 else "FAIL"), summary[:80], rc


def main(argv: list[str]) -> int:
    pos = [a for a in argv if not a.startswith("--")]
    root = pos[0] if pos else str(lib.find_repo_root())
    print(f"root: {root}")
    rows = []
    worst = 0
    for name, script in AUDITS:
        verdict, summary, rc = _run(name, [sys.executable, str(HERE / script), root])
        worst = max(worst, rc)
        rows.append((name, verdict, summary))

    # graph drift: opt-in. SKIP (not FAIL) when no snapshot exists yet.
    snapshot = lib.find_repo_root() / "graph" / "nodes.jsonl"
    if GRAPH.is_file() and snapshot.is_file():
        verdict, summary, rc = _run("graph_verify", [sys.executable, str(GRAPH), "verify"])
        worst = max(worst, rc)
        rows.append(("graph_verify", verdict, summary))
    else:
        rows.append(("graph_verify", "SKIP", "no snapshot — graph build not run"))

    print(f"{'audit':<16}{'verdict':<9}summary")
    print("-" * 70)
    for name, verdict, summary in rows:
        print(f"{name:<16}{verdict:<9}{summary}")
    print("-" * 70)
    fails = [n for n, v, _ in rows if v == "FAIL"]
    print(f"{'ALL PASS' if not fails else 'FAIL: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
