#!/usr/bin/env python3
"""eval — run live UX-flow evaluations: whole or selectively. The front door.

A standardized evaluations module. Each flow mirrors one expected user UX flow on
the live deploy (PROJECT.md §1). Run the whole suite for full regression, or a
named flow / tag subset for fast iteration. Every change that touches a user-
facing surface should map to at least one flow here (regression_protocol.md §4).

Usage:
  eval list [--json]                 list flows + tags
  eval run [--tag T] [--json]        run all flows (or only those tagged T)
  eval run <name> [<name> ...]       run named flow(s)
  eval run --target URL ...          override the live target (default: PROJECT.md LIVE_TARGET)

Flows live in evals/flows/*.py; each exposes module-level `FLOWS: list[Flow]`.
Resolves LIVE_TARGET + FINDINGS_DIR from PROJECT.md §0. Records one metric row per
flow to the evidence ledger.

Exit: 0 all pass / 1 any flow failed / 2 usage or no flows.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import flow as F

# reuse agent_tooling bindings parse (C1) — load by path to dodge name clash.
_atl = Path(__file__).resolve().parent.parent / "agent_tooling" / "lib.py"
_spec = importlib.util.spec_from_file_location("agent_tooling_lib", _atl)
atl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(atl)

FLOWS_DIR = Path(__file__).resolve().parent / "flows"


def discover() -> dict[str, F.Flow]:
    """Import every flows/*.py and collect their module-level FLOWS lists."""
    registry: dict[str, F.Flow] = {}
    if not FLOWS_DIR.is_dir():
        return registry
    for fp in sorted(FLOWS_DIR.glob("*.py")):
        if fp.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"evalflow_{fp.stem}", fp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for fl in getattr(mod, "FLOWS", []):
            registry[fl.name] = fl
    return registry


def _target(argv: list[str]) -> str:
    if "--target" in argv:
        i = argv.index("--target")
        if i + 1 < len(argv):
            return argv[i + 1]
    bound = atl.binding("LIVE_TARGET")
    if not atl.is_set(bound):
        atl.die("no live target: set LIVE_TARGET in PROJECT.md §0 or pass --target URL", 2)
    return bound


def _nonce() -> str:
    return "EVAL_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _record(flow_name: str, ok: bool, nonce: str) -> None:
    """Append one metric row to the evidence ledger (P7). Best-effort."""
    findings = atl.binding("FINDINGS_DIR", "docs/findings")
    if not atl.is_set(findings):
        return
    out = atl.find_repo_root() / findings / "evidence" / "evals.jsonl"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(),
               "nonce": nonce, "flow": flow_name,
               "result": "pass" if ok else "fail"}
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        pass


def cmd_list(argv: list[str]) -> int:
    reg = discover()
    if "--json" in argv:
        print(json.dumps([{"name": f.name, "tags": list(f.tags),
                           "description": f.description, "steps": len(f.steps)}
                          for f in reg.values()], indent=2))
        return 0
    if not reg:
        print("no flows in evals/flows/")
        return 0
    for f in reg.values():
        tags = f" [{', '.join(f.tags)}]" if f.tags else ""
        print(f"{f.name:<24}{len(f.steps)} steps{tags}  {f.description}")
    return 0


def _select(reg: dict[str, F.Flow], argv: list[str]) -> list[F.Flow]:
    names = [a for a in argv[1:]
             if not a.startswith("--") and argv[argv.index(a) - 1] != "--target"]
    if "--tag" in argv:
        i = argv.index("--tag")
        tag = argv[i + 1] if i + 1 < len(argv) else ""
        return [f for f in reg.values() if tag in f.tags]
    if names:
        return [reg[n] for n in names if n in reg]
    return list(reg.values())


def cmd_run(argv: list[str]) -> int:
    reg = discover()
    if not reg:
        atl.die("no flows to run (evals/flows/ empty)", 2)
    selected = _select(reg, argv)
    if not selected:
        atl.die("no flows matched the selection", 2)
    target = _target(argv)
    nonce = _nonce()
    json_mode = "--json" in argv
    print(f"eval target: {target}  nonce: {nonce}")

    results: list[F.FlowResult] = []
    for fl in selected:
        ctx = F.EvalContext(live_target=target, nonce=nonce)
        res = F.run_flow(fl, ctx)
        results.append(res)
        _record(fl.name, res.ok, nonce)
        if not json_mode:
            for s in res.steps:
                mark = "ok  " if s.ok else "FAIL"
                print(f"  {mark} {fl.name}/{s.name}: {s.digest} ({s.wall_ms}ms)")
            verdict = "PASS" if res.ok else "FAIL"
            extra = "" if res.cleanup_ok else " [cleanup FAILED]"
            ret = f" retained={len(res.retained)}" if res.retained else ""
            print(f"  -> {verdict} {fl.name} ({res.wall_ms}ms){ret}{extra}")

    failed = [r.name for r in results if not r.ok]
    if json_mode:
        print(json.dumps([{"flow": r.name, "ok": r.ok,
                           "steps": [{"name": s.name, "ok": s.ok, "digest": s.digest}
                                     for s in r.steps],
                           "retained": r.retained} for r in results], indent=2))
    print(f"{'ALL PASS' if not failed else 'FAIL: ' + ', '.join(failed)} "
          f"({len(results)} flow(s))")
    return 0 if not failed else 1


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd, rest = argv[0], argv
    if cmd == "list":
        return cmd_list(rest)
    if cmd == "run":
        return cmd_run(rest)
    atl.die(f"unknown command '{cmd}'. use: list | run")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
