#!/usr/bin/env python3
"""Regression bench — live, dev-sign-driven acceptance battery for PathfinderIQ.

Drives a small battery of real chat turns against a deployed instance and
asserts, per turn, the operator's hard floor:

  * exactly one terminal frame and it is ``done`` (not ``error``/``aborted``);
  * zero error envelopes in any ``tool_result`` (no ``GraphSyntaxException``,
    no ``"error": true``, no ``"status": "failed"``, no ``internal_error``);
  * at least ``min_tool_calls`` tool calls fired (proves the agent did work,
    did not just answer from the prompt);
  * every ``must_include`` evidence token appears in the stream (proves the
    answer is grounded in the live graph/telemetry/search, not hallucinated);
  * wall-clock under ``budget_s``.

This is the repeatable gate to run before every deploy. Lineage: GridIQ
``/tmp/regression/run_all.py`` (SB-DEV-BENCH), now a first-class script.

Auth: signs every request with the Ed25519 dev-sign key, so it runs against an
``AUTH_ENABLED=true`` deployment without an interactive Entra login. The server
must have ``DEV_PUBLIC_KEY_ED25519`` set to the matching public key.

Usage:
    PYTHONPATH=app/backend python3 scripts/regression_bench.py \
        --base-url https://<fqdn> [--only investigate] [--budget 300]

Exit codes: 0 = every case passed; 1 = a case failed; 2 = could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

try:
    from agentkit.dev_tools.dev_sign import _sign_headers
except Exception as exc:  # pragma: no cover
    print(f"FATAL: cannot import dev-sign signer ({exc}). "
          "Run with PYTHONPATH=app/backend.", file=sys.stderr)
    raise SystemExit(2)

# Error markers scanned across the whole stream (case-insensitive).
ERROR_MARKERS = (
    "graphsyntaxexception",
    "unexpected token",
    '"error": true',
    '"error":true',
    '\\"status\\": \\"failed\\"',
    '\\"status\\": \\"error\\"',
    "internal_error",
    "tool_error",
)
TERMINAL_EVENTS = {"done", "error", "aborted"}
BYTE_CAP = 8_000_000


@dataclass
class Case:
    name: str
    agent: str
    prompt: str
    min_tool_calls: int
    must_include: tuple[str, ...]
    budget_s: float = 300.0
    # Sub-agent tool names that must appear on the /api/sessions/{id}/events
    # delegation channel (proves the orchestrator's specialists actually ran
    # the tool, and that the events channel is dev-sign-observable).
    subagent_tools: tuple[str, ...] = ()


@dataclass
class Result:
    name: str
    ok: bool
    duration_s: float
    tool_calls: int
    tool_results: int
    terminal: str
    violations: list[str] = field(default_factory=list)


# The battery. Each case is a real end-to-end turn against the live deploy.
CASES: list[Case] = [
    Case(
        name="investigate",
        agent="orchestrator",
        prompt=(
            "A fibre cut is detected on the Sydney-Melbourne corridor. Use the "
            "graph to investigate: for the affected transport links, trace each "
            "link's conduit routing and the inline amplifiers feeding it, and "
            "enumerate the customer services and their governing SLAs that "
            "traverse the cut. Run the graph traversals now."
        ),
        # Evidence that can ONLY come from the live graph traversals — the
        # in('amplifies') leg (amplifiers) and the in('governs') leg (SLAs).
        min_tool_calls=3,
        must_include=("CONDUIT-SYD-MEL", "AMP-SYD-MEL", "SLA-"),
        budget_s=300.0,
        subagent_tools=("query_graph",),
    ),
    Case(
        name="graph_direct",
        agent="networkInvestigator",
        prompt=(
            "Query the graph for transport link LINK-SYD-MEL-FIBRE-01: its "
            "endpoints, the conduit it routes through, and the inline "
            "amplifiers that feed it. Use the graph traversal tool."
        ),
        # A single direct turn reliably engages the asked-for entity and runs
        # a graph tool; the deeper conduit/amplifier evidence is asserted by
        # the orchestrated `investigate` case (a terse one-shot answer may
        # name the entity without echoing every downstream ID).
        min_tool_calls=1,
        must_include=("LINK-SYD-MEL-FIBRE-01",),
        budget_s=180.0,
    ),
]


def _signed(method: str, path: str, body: bytes) -> dict[str, str]:
    h = _sign_headers(method=method, path_and_query=path, body=body, context_slug="bench")
    h["Content-Type"] = "application/json"
    return h


def _post_json(base: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=body, headers=_signed("POST", path, body), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


class _EventsSubscriber:
    """Background subscriber to the /api/sessions/{id}/events delegation channel.

    Signs the GET with the dev-sign key (the events endpoint honours the
    dev-sign principal), streams the broadcast SSE, and accumulates the raw
    payload so the bench can assert sub-agent tool calls were emitted.
    """

    def __init__(self, base: str, sid: str):
        path = f"/api/sessions/{sid}/events"
        self._req = urllib.request.Request(
            base + path, headers=_signed("GET", path, b""), method="GET")
        self._resp = None
        self._blob_parts: list[str] = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._error: str | None = None

    def _run(self) -> None:
        try:
            self._resp = urllib.request.urlopen(self._req, timeout=600)
            for raw in self._resp:
                self._blob_parts.append(raw.decode("utf-8", "replace").lower())
        except Exception as e:  # closed by stop(), or transient
            self._error = str(e)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> str:
        try:
            if self._resp is not None:
                self._resp.close()
        except Exception:
            pass
        self._thread.join(timeout=5)
        return "".join(self._blob_parts)


def _run_case(base: str, case: Case) -> Result:
    started = time.monotonic()
    # 1. Fresh session per case (avoids cross-case thread bleed).
    try:
        session = _post_json(base, "/api/sessions", {"title": f"bench-{case.name}"})
        sid = session.get("id")
        if not sid:
            return Result(case.name, False, 0.0, 0, 0, "", ["session create returned no id"])
    except urllib.error.HTTPError as e:
        return Result(case.name, False, 0.0, 0, 0, "",
                      [f"session create HTTP {e.code} (dev-sign key set on server?)"])
    except Exception as e:
        return Result(case.name, False, 0.0, 0, 0, "", [f"session create failed: {e}"])

    # 1b. Subscribe to the delegation event channel (sub-agent tool calls).
    subscriber = None
    if case.subagent_tools:
        subscriber = _EventsSubscriber(base, sid)
        subscriber.start()

    # 2. Drive the turn, stream the SSE.
    path = f"/api/chat/{sid}?agent_id={case.agent}"
    body = json.dumps({"content": case.prompt}).encode()
    req = urllib.request.Request(base + path, data=body, headers=_signed("POST", path, body), method="POST")

    events: list[str] = []
    starts = ends = tool_results = 0
    total = 0
    blob_lower_parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=case.budget_s + 60) as r:
            for raw in r:
                total += len(raw)
                if total > BYTE_CAP:
                    return Result(case.name, False, time.monotonic() - started, starts,
                                  tool_results, "", [f"byte cap exceeded ({total})"])
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    et = line[6:].strip()
                    events.append(et)
                    if et == "tool_call_start":
                        starts += 1
                    elif et == "tool_call_end":
                        ends += 1
                    elif et == "tool_result":
                        tool_results += 1
                elif line.startswith("data:"):
                    blob_lower_parts.append(line[5:].lower())
    except Exception as e:
        return Result(case.name, False, time.monotonic() - started, starts,
                      tool_results, "", [f"chat stream failed: {e}"])

    duration = time.monotonic() - started
    blob_lower = "".join(blob_lower_parts)
    violations: list[str] = []

    # Collect the delegation event channel (sub-agent tool calls).
    events_blob = subscriber.stop() if subscriber is not None else ""
    for tool_name in case.subagent_tools:
        if tool_name.lower() not in events_blob:
            violations.append(
                f"sub-agent tool {tool_name!r} not seen on /events channel")

    terminals = [e for e in events if e in TERMINAL_EVENTS]
    terminal = terminals[-1] if terminals else "<none>"
    if len(terminals) != 1 or terminal != "done":
        violations.append(f"terminal frame = {terminals or '<none>'} (want exactly ['done'])")
    if starts != ends:
        violations.append(f"tool_call_start/end mismatch: {starts} vs {ends}")
    if starts < case.min_tool_calls:
        violations.append(f"only {starts} tool calls (< min {case.min_tool_calls})")
    for marker in ERROR_MARKERS:
        if marker in blob_lower:
            violations.append(f"error marker present: {marker!r}")
    for token in case.must_include:
        if token.lower() not in blob_lower:
            violations.append(f"missing evidence token: {token!r}")
    if duration > case.budget_s:
        violations.append(f"over budget: {duration:.0f}s > {case.budget_s:.0f}s")

    return Result(case.name, not violations, duration, starts, tool_results, terminal, violations)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--only", default=None, help="run a single case by name")
    ap.add_argument("--budget", type=float, default=None, help="override every case latency budget (s)")
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")

    cases = CASES
    if args.only:
        cases = [c for c in CASES if c.name == args.only]
        if not cases:
            print(f"FATAL: no case named {args.only!r}. Have: {[c.name for c in CASES]}", file=sys.stderr)
            return 2
    if args.budget is not None:
        for c in cases:
            c.budget_s = args.budget

    results: list[Result] = []
    for c in cases:
        print(f"--- running {c.name} (agent={c.agent}, budget={c.budget_s:.0f}s) ...", flush=True)
        res = _run_case(base, c)
        results.append(res)
        verdict = "PASS" if res.ok else "FAIL"
        print(f"    {verdict} {c.name}: {res.duration_s:.0f}s tool_calls={res.tool_calls} "
              f"tool_results={res.tool_results} terminal={res.terminal}")
        for v in res.violations:
            print(f"      - {v}")

    passed = sum(1 for r in results if r.ok)
    print(f"\n=== bench: {passed}/{len(results)} passed ===")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
