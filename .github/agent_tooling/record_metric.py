#!/usr/bin/env python3
"""record_metric — append a metric row to the evidence ledger (P7).

Turns "I checked" into recorded evidence. JSONL, one row per call.

Usage:
  record_metric --metric latency_ms --value 42 --threshold "<=100" \\
                [--nonce RUN_...] [--evidence-dir DIR] [--fail-on-miss]

Default evidence dir: <FINDINGS_DIR>/evidence/metrics.jsonl
Exit: 0 ok (or pass) / 1 --fail-on-miss and value misses threshold / 2 usage.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def opt(argv: list[str], name: str, default: str | None = None) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def check_threshold(value: str, threshold: str) -> bool | None:
    """Return True/False if numeric comparison resolvable, else None."""
    m = re.match(r"\s*(<=|>=|<|>|==|=)\s*(-?\d+(?:\.\d+)?)\s*$", threshold)
    if not m:
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    op, bound = m.group(1), float(m.group(2))
    return {
        "<=": v <= bound, ">=": v >= bound, "<": v < bound,
        ">": v > bound, "==": v == bound, "=": v == bound,
    }[op]


def main(argv: list[str]) -> int:
    metric = opt(argv, "--metric")
    value = opt(argv, "--value")
    if not metric or value is None:
        lib.die("usage: record_metric --metric M --value V [--threshold T] [--fail-on-miss]")
    threshold = opt(argv, "--threshold", "")
    nonce = opt(argv, "--nonce", "")
    ev_dir = opt(argv, "--evidence-dir")

    passed = check_threshold(value, threshold) if threshold else None
    row = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "nonce": nonce,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "result": "pass" if passed else ("fail" if passed is False else "recorded"),
    }

    if ev_dir:
        out = (lib.find_repo_root() / ev_dir).resolve()
    else:
        fdir = lib.binding("FINDINGS_DIR", "docs/findings")
        out = (lib.find_repo_root() / fdir / "evidence").resolve()
    out.mkdir(parents=True, exist_ok=True)
    ledger = out / "metrics.jsonl"
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")

    print(json.dumps(row))
    print(f"-> {lib.rel(ledger)}")
    if "--fail-on-miss" in argv and passed is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
