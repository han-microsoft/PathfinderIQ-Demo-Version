#!/usr/bin/env python3
"""SSE contract probe — live wire-contract assertion for PathfinderIQ chat.

Drives one real chat round-trip against a deployed instance and asserts the
foreground SSE event-sequence contract (lineage: GridIQ
``scripts/sse_contract_probe.py``):

  * exactly one terminal frame (``done`` | ``error`` | ``aborted``);
  * every ``tool_call_start`` has a matching ``tool_call_end`` (id-paired);
  * at least one ``tool_result`` when tools were called;
  * only known event names appear;
  * total streamed bytes stay under a sane cap.

Auth: signs every request with the Ed25519 dev-sign key (so it works against an
``AUTH_ENABLED=true`` deployment without an interactive Entra login). The server
must have ``DEV_PUBLIC_KEY_ED25519`` set to the matching public key.

Usage:
    PYTHONPATH=app/backend python3 scripts/sse_contract_probe.py \
        --base-url https://<fqdn> [--agent networkInvestigator] \
        [--prompt "..."]

Exit codes: 0 = contract held; 1 = contract violated; 2 = could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

try:
    from agentkit.dev_tools.dev_sign import _sign_headers
except Exception as exc:  # pragma: no cover
    print(f"FATAL: cannot import dev-sign signer ({exc}). "
          "Run with PYTHONPATH=app/backend.", file=sys.stderr)
    raise SystemExit(2)

KNOWN_EVENTS = {
    "token", "tool_call_start", "tool_call_delta", "tool_call_end",
    "tool_result", "thinking", "citation", "metadata", "done", "error",
    "aborted", "rate_limited", "keepalive",
}
TERMINAL_EVENTS = {"done", "error", "aborted"}
BYTE_CAP = 5_000_000


def _signed(method: str, path: str, body: bytes) -> dict[str, str]:
    h = _sign_headers(method=method, path_and_query=path, body=body, context_slug="probe")
    h["Content-Type"] = "application/json"
    return h


def _post_json(base: str, path: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=body, headers=_signed("POST", path, body), method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--agent", default="networkInvestigator")
    ap.add_argument("--prompt", default="Query the graph for LINK-SYD-MEL-FIBRE-01 endpoints and summarize.")
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")

    try:
        session = _post_json(base, "/api/sessions", {"title": "sse-probe"})
        sid = session.get("id")
        if not sid:
            print("FATAL: session create returned no id", file=sys.stderr)
            return 2
    except urllib.error.HTTPError as e:
        print(f"FATAL: session create HTTP {e.code} (dev-sign key set on server?)", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FATAL: session create failed: {e}", file=sys.stderr)
        return 2

    path = f"/api/chat/{sid}?agent_id={args.agent}"
    body = json.dumps({"content": args.prompt}).encode()
    req = urllib.request.Request(base + path, data=body, headers=_signed("POST", path, body), method="POST")

    events: list[str] = []
    starts: list[str] = []
    ends: list[str] = []
    tool_results = 0
    total = 0
    event_type = None
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            for raw in r:
                total += len(raw)
                if total > BYTE_CAP:
                    print(f"FAIL: byte cap exceeded ({total} > {BYTE_CAP})")
                    return 1
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    events.append(event_type)
                    if event_type == "tool_call_start":
                        starts.append(line)
                    elif event_type == "tool_call_end":
                        ends.append(line)
                    elif event_type == "tool_result":
                        tool_results += 1
    except Exception as e:
        print(f"FATAL: chat stream failed: {e}", file=sys.stderr)
        return 2

    violations: list[str] = []
    unknown = sorted(set(events) - KNOWN_EVENTS)
    if unknown:
        violations.append(f"unknown event names: {unknown}")
    terminals = [e for e in events if e in TERMINAL_EVENTS]
    if len(terminals) != 1:
        violations.append(f"expected exactly 1 terminal frame, got {terminals}")
    if len(starts) != len(ends):
        violations.append(f"tool_call_start/end mismatch: {len(starts)} starts vs {len(ends)} ends")
    if starts and tool_results == 0:
        violations.append("tools called but no tool_result frame")

    print(f"events={len(events)} starts={len(starts)} ends={len(ends)} "
          f"tool_results={tool_results} terminal={terminals} bytes={total}")
    if violations:
        for v in violations:
            print("FAIL:", v)
        return 1
    print("SSE_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
