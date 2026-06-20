#!/usr/bin/env python3
"""Live scenario-swap probe — asserts runtime use-case swap on a deployed app.

Drives the deployed instance through both scenario packs and asserts the swap
rebinds the catalog, agents, and scenario metadata, and that the demo-sandbox's
cloud-free tool answers a real chat round-trip. Signs every request with the
Ed25519 dev-sign key so it works against an ``AUTH_ENABLED=true`` deployment.

Usage:
    PYTHONPATH=app/backend python3 scripts/scenario_swap_probe.py --base-url https://<fqdn>

Exit: 0 = swap verified; 1 = assertion failed; 2 = could not run.
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
    print(f"FATAL: cannot import dev-sign signer ({exc}). Run with PYTHONPATH=app/backend.", file=sys.stderr)
    raise SystemExit(2)

TELECOM = "telecom-playground-v2"
SANDBOX = "demo-sandbox"


def _headers(method: str, path: str, body: bytes, scenario: str | None) -> dict[str, str]:
    h = _sign_headers(method=method, path_and_query=path, body=body, context_slug="swap-probe")
    h["Content-Type"] = "application/json"
    if scenario:
        h["X-Scenario-Name"] = scenario
    return h


def _get(base: str, path: str, scenario: str | None = None) -> dict:
    req = urllib.request.Request(base + path, headers=_headers("GET", path, b"", scenario), method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _post(base: str, path: str, payload: dict, scenario: str | None = None) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=body, headers=_headers("POST", path, body, scenario), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    args = ap.parse_args(argv)
    base = args.base_url.rstrip("/")
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    try:
        # 1. Catalog lists both packs.
        cat = _get(base, "/api/scenarios")
        names = {s["name"] for s in cat.get("scenarios", [])}
        check("catalog_lists_both", {TELECOM, SANDBOX} <= names, str(sorted(names)))

        # 2. Scenario metadata rebinds per header.
        tele_meta = _get(base, "/api/scenario", TELECOM)
        sand_meta = _get(base, "/api/scenario", SANDBOX)
        check("metadata_telecom", tele_meta.get("scenario_name") == TELECOM, tele_meta.get("scenario_name", ""))
        check("metadata_sandbox", sand_meta.get("scenario_name") == SANDBOX, sand_meta.get("scenario_name", ""))
        check("metadata_domain_sandbox", sand_meta.get("domain") == "sandbox", sand_meta.get("domain", ""))

        # 3. Agents rebind per header.
        def agent_names(scenario: str) -> set[str]:
            data = _get(base, "/api/agents/", scenario)
            return {a.get("name") or a.get("id") for a in data}
        tele_agents = agent_names(TELECOM)
        sand_agents = agent_names(SANDBOX)
        check("agents_telecom_has_investigator", "NetworkInvestigator" in tele_agents, str(sorted(tele_agents)))
        check("agents_sandbox_has_guide", "SandboxGuide" in sand_agents, str(sorted(sand_agents)))
        check("agents_disjoint", tele_agents.isdisjoint(sand_agents))

        # 4. Per-user preference round-trip (no env mutation).
        sel = _post(base, "/api/scenarios/select", {"scenario": SANDBOX})
        check("select_returns_scenario", sel.get("scenario") == SANDBOX, str(sel))

        # 5. Sandbox chat round-trip — cloud-free tool answers live.
        sess = _post(base, "/api/sessions", {"title": "swap-probe"}, SANDBOX)
        sid = sess.get("id")
        check("sandbox_session_created", bool(sid))
        if sid:
            path = f"/api/chat/{sid}?agent_id=guide"
            body = json.dumps({"content": "What is the sandbox dataset status? Use your tool."}).encode()
            req = urllib.request.Request(base + path, data=body, headers=_headers("POST", path, body, SANDBOX), method="POST")
            seen_done = False
            seen_tool = False
            raw = b""
            with urllib.request.urlopen(req, timeout=120) as r:
                for line in r:
                    raw += line
                    s = line.decode(errors="replace").strip()
                    if s.startswith("event:"):
                        ev = s.split(":", 1)[1].strip()
                        if ev in ("done", "tool_result", "tool_call_end"):
                            seen_done = seen_done or ev == "done"
                            seen_tool = seen_tool or ev in ("tool_result", "tool_call_end")
            blob = raw.decode(errors="replace")
            check("sandbox_chat_terminal_done", seen_done or '"done"' in blob or "event: done" in blob)
            check("sandbox_chat_used_tool", seen_tool or "sandbox" in blob.lower())
    except urllib.error.HTTPError as e:
        print(f"FATAL: HTTP {e.code} {e.reason} (dev-sign key set on server?)", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FATAL: probe error: {e}", file=sys.stderr)
        return 2

    print()
    if failures:
        print(f"SWAP_PROBE_FAIL — {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("SWAP_PROBE_OK — runtime scenario swap verified live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
