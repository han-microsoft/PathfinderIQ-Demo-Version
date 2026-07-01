#!/usr/bin/env python3
"""PathfinderIQ evaluation harness — scored incident battery over a live deploy.

Lineage: GridIQ ``evaluations/harness`` (domain-agnostic runner + thin adapter).
This is the thin PathfinderIQ adapter + runner in one file: it drives the live
chat surface for each case in ``cases.yaml``, captures the agent's tool-call
sequence + final answer, and scores three gates by observable-token coverage:

  Gate 1 — detection: did the agent name the event class / breach?
  Gate 2 — investigation: did it reach the ground-truth observables (element ids,
           mechanism, blast radius)?
  Gate 3 — recommendation: are the actions aligned + free of over-reach?

Scoring is token coverage per gate (an observable = a synonym list, OR-matched).
It is intentionally simple + transparent — a screening signal, not a judge.

Auth: signs every request with the Ed25519 dev-sign key (works against
AUTH_ENABLED=true). Serial only (the deploy rejects overlapping per-session
turns). Writes per-run JSON + SUMMARY.md under --out.

Usage:
    PYTHONPATH=app/backend python3 graph_data/eval/run_eval.py \
        --base-url https://<fqdn> [--agent networkInvestigator] [--only <id>] \
        [--runs 1] [--out graph_data/eval/results]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import yaml

try:
    from agentkit.dev_tools.dev_sign import _sign_headers
except Exception as exc:  # pragma: no cover
    print(f"FATAL: cannot import dev-sign signer ({exc}). Run with PYTHONPATH=app/backend.",
          file=sys.stderr)
    raise SystemExit(2)

HERE = Path(__file__).resolve().parent


def _headers(method: str, path: str, body: bytes, scenario: str) -> dict[str, str]:
    h = _sign_headers(method=method, path_and_query=path, body=body, context_slug="evalharness")
    h["Content-Type"] = "application/json"
    h["X-Scenario-Name"] = scenario
    return h


def _post(base: str, path: str, payload: dict, scenario: str) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=body,
                                 headers=_headers("POST", path, body, scenario), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _drive_chat(base: str, scenario: str, agent: str, prompt: str, timeout: int = 240) -> dict:
    """Run one chat turn; return {text, tools, event_counts, elapsed}."""
    sid = _post(base, "/api/sessions", {"title": "eval"}, scenario).get("id")
    path = f"/api/chat/{sid}?agent_id={agent}"
    body = json.dumps({"content": prompt}).encode()
    req = urllib.request.Request(base + path, data=body,
                                 headers=_headers("POST", path, body, scenario), method="POST")
    cur = None
    toks: list[str] = []
    tools: list[str] = []
    counts: dict[str, int] = {}
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event:"):
                cur = line[6:].strip()
                counts[cur] = counts.get(cur, 0) + 1
            elif line.startswith("data:"):
                d = line[5:].strip()
                if cur == "token":
                    try:
                        j = json.loads(d)
                        toks.append(j.get("token", "") if isinstance(j, dict) else str(j))
                    except Exception:
                        toks.append(d)
                elif cur == "tool_call_start":
                    try:
                        j = json.loads(d)
                        name = j.get("tool") or j.get("name") or (j.get("data") or {}).get("tool")
                        if name:
                            tools.append(str(name))
                    except Exception:
                        pass
    return {"text": "".join(toks), "tools": tools, "event_counts": counts,
            "elapsed": round(time.time() - t0, 1)}


import re

_NEG_CUES = ("no ", "not ", "never ", "without ", "ruled out", "rule out", "isn't",
             "aren't", "wasn't", "weren't", "within tolerance", "absence of",
             "rather than", "instead of", "unlikely", "excluded", "avoid")


def _norm(s: str) -> str:
    """Lowercase + treat hyphen/slash as space so 'load-balancing' == 'load balancing'."""
    return re.sub(r"\s+", " ", re.sub(r"[-/]", " ", str(s).lower()))


def _score_gate(text_norm: str, observables: list) -> tuple[int, int, list[str]]:
    hit = 0
    misses: list[str] = []
    for obs in observables or []:
        syns = obs if isinstance(obs, list) else [obs]
        if any(_norm(s) in text_norm for s in syns):
            hit += 1
        else:
            misses.append("|".join(str(s) for s in syns))
    return hit, len(observables or []), misses


def _forbidden_hits(text_norm: str, forbidden: list) -> list[str]:
    """Negation-aware: a forbidden phrase only counts as over-reach when it appears
    WITHOUT a nearby preceding negation cue (so 'ruled out fronthaul' / 'not
    critical' do not false-flag)."""
    hits: list[str] = []
    for f in forbidden or []:
        fn = _norm(f)
        for m in re.finditer(re.escape(fn), text_norm):
            window = text_norm[max(0, m.start() - 45):m.start()]
            if not any(cue in window for cue in _NEG_CUES):
                hits.append(str(f))
                break
    return hits


def _score_case(case: dict, text: str) -> dict:
    low = _norm(text)
    g1 = _score_gate(low, case.get("gate1_detection"))
    g2 = _score_gate(low, case.get("gate2_investigation"))
    g3 = _score_gate(low, case.get("gate3_recommendation"))
    forbidden_hits = _forbidden_hits(low, case.get("forbidden", []))
    return {
        "gate1": {"hit": g1[0], "total": g1[1], "miss": g1[2]},
        "gate2": {"hit": g2[0], "total": g2[1], "miss": g2[2]},
        "gate3": {"hit": g3[0], "total": g3[1], "miss": g3[2]},
        "forbidden_hits": forbidden_hits,
    }


def _verdict(sc: dict) -> str:
    def rate(g):
        return (g["hit"] / g["total"]) if g["total"] else 1.0
    r1, r2 = rate(sc["gate1"]), rate(sc["gate2"])
    over = bool(sc["forbidden_hits"])
    if r1 >= 0.5 and r2 >= 0.6 and not over:
        return "pass"
    if r1 >= 0.5 and r2 >= 0.3:
        return "partial"
    return "fail"


def _write_summary(out: Path, scenario: str, agent: str, runs: int, rows: list) -> list[str]:
    lines = ["# PathfinderIQ eval — O-RAN battery", "",
             f"- scenario: `{scenario}`  agent: `{agent}`  runs/case: {runs}",
             f"- cases: {len(rows)}", "",
             "| case | class | sev | split | verdict | G1 | G2 | G3 | tools | over |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    npass = 0
    ho_pass = ho_total = 0
    for r in rows:
        s = r["score"]
        v = r["verdict"]
        npass += v == "pass"
        if r["split"] == "held_out":
            ho_total += 1
            ho_pass += v == "pass"
        lines.append(
            f"| {r['case_id']} | {r['event_class']} | {r['severity']} | {r['split']} | "
            f"**{v}** | {s['gate1']['hit']}/{s['gate1']['total']} | "
            f"{s['gate2']['hit']}/{s['gate2']['total']} | {s['gate3']['hit']}/{s['gate3']['total']} | "
            f"{len(r.get('tools', []))} | {'⚠' if r['score']['forbidden_hits'] else ''} |")
    lines += ["",
              f"**Pass rate:** {npass}/{len(rows)}"
              + (f"  ·  held-out: {ho_pass}/{ho_total}" if ho_total else ""),
              "",
              "Gate-1 detection + Gate-2 investigation are scored from the agent's answer "
              "(observable-token coverage, negation-aware over-reach check). Gate-3 is a "
              "lighter recommendation signal; full Gate-3 synthesis is best seen via the "
              "`orchestrator` agent.", ""]
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="")
    ap.add_argument("--cases", default=str(HERE / "cases.yaml"))
    ap.add_argument("--agent", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--rescore", action="store_true",
                    help="Recompute verdicts/SUMMARY from saved __run*.json transcripts (no live calls).")
    args = ap.parse_args(argv)

    spec = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    scenario = spec["scenario"]
    agent = args.agent or spec.get("agent", "networkInvestigator")
    cases = [c for c in spec["cases"] if not args.only or c["id"] == args.only]
    case_by_id = {c["id"]: c for c in spec["cases"]}
    base = args.base_url.rstrip("/")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.rescore:
        rows = []
        for jf in sorted(out.glob("*__run*.json")):
            rec = json.loads(jf.read_text(encoding="utf-8"))
            case = case_by_id.get(rec["case_id"])
            if not case:
                continue
            rec["score"] = _score_case(case, rec.get("final_text", ""))
            rec["verdict"] = _verdict(rec["score"])
            jf.write_text(json.dumps(rec, indent=2), encoding="utf-8")
            rows.append(rec)
            s = rec["score"]
            print(f"  {rec['case_id']:26s} {rec['verdict']:7s} "
                  f"G1 {s['gate1']['hit']}/{s['gate1']['total']} "
                  f"G2 {s['gate2']['hit']}/{s['gate2']['total']} "
                  f"G3 {s['gate3']['hit']}/{s['gate3']['total']}"
                  + (f" OVERREACH={s['forbidden_hits']}" if s["forbidden_hits"] else ""))
        lines = _write_summary(out, scenario, agent, args.runs, rows)
        print("\n".join(lines[4:]))
        print(f"\nwrote {out}/SUMMARY.md")
        return 0

    if not base:
        print("FATAL: --base-url required for a live run (use --rescore for offline).", file=sys.stderr)
        return 2

    rows = []
    for case in cases:
        best = None
        for run in range(args.runs):
            try:
                res = _drive_chat(base, scenario, agent, case["seed_prompt"])
            except Exception as e:
                print(f"  {case['id']} run{run}: ERROR {e}", file=sys.stderr)
                continue
            sc = _score_case(case, res["text"])
            sc_total = sum(sc[g]["hit"] for g in ("gate1", "gate2", "gate3"))
            rec = {"case_id": case["id"], "run": run, "split": case.get("split"),
                   "event_class": case.get("event_class"), "severity": case.get("severity"),
                   "agent": agent, "verdict": _verdict(sc), "score": sc,
                   "tools": res["tools"], "elapsed": res["elapsed"],
                   "event_counts": res["event_counts"], "final_text": res["text"]}
            (out / f"{case['id']}__run{run}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
            if best is None or sc_total > sum(best["score"][g]["hit"] for g in ("gate1", "gate2", "gate3")):
                best = rec
            print(f"  {case['id']:26s} run{run} {rec['verdict']:7s} "
                  f"G1 {sc['gate1']['hit']}/{sc['gate1']['total']} "
                  f"G2 {sc['gate2']['hit']}/{sc['gate2']['total']} "
                  f"G3 {sc['gate3']['hit']}/{sc['gate3']['total']} "
                  f"tools={len(res['tools'])} {res['elapsed']}s"
                  + (f" OVERREACH={sc['forbidden_hits']}" if sc["forbidden_hits"] else ""))
            time.sleep(4)  # per-session concurrency guard / autoscale dup-turn avoidance
        if best:
            rows.append(best)

    lines = _write_summary(out, scenario, agent, args.runs, rows)
    print("\n".join(lines[4:]))
    print(f"\nwrote {out}/SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
