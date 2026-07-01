#!/usr/bin/env python3
"""Idempotent C-suite enhancement of the telecom-playground-v2 replay.

Adds three clarity-first beats to the scripted demo (safe to re-run):

  1. Operator-approves-dispatch — a `present_options` card (single dispatch vs
     two-team) BEFORE the field dispatch, so the human stays in control.
  2. Work IQ stakeholder context — an `ask_work_iq` call in the comms thread
     surfacing customer escalation contacts + the 15-minute SLA notification
     clock + the prior governance note on the shared-conduit risk.
  3. SLA dollars-saved forecast + adaptive-severity rationale in the
     orchestrator summary.

Operates on the ACTIVE served file (scenario ui/replay_conversation.json).
Each insertion is guarded by a marker check, so running twice is a no-op.
"""

import json
from pathlib import Path

REPLAY = (
    Path(__file__).resolve().parents[3]
    / "graph_data/data/scenarios/telecom-playground-v2/ui/replay_conversation.json"
)


def _assistant(thread):
    return next(m for m in thread["messages"] if m["role"] == "assistant")


def main() -> None:
    d = json.loads(REPLAY.read_text())
    th = d["threads"]
    changed = []

    # ── 1. Orchestrator: operator-approves-dispatch options ──────────────────
    orch = _assistant(th["orchestrator"])
    otcs = orch["tool_calls"]
    if not any(tc["id"] == "call_dispatch_options" for tc in otcs):
        idx = next(i for i, tc in enumerate(otcs) if tc["id"] == "call_dispatch_dave")
        options_tc = {
            "id": "call_dispatch_options",
            "name": "present_options",
            "arguments": {
                "prompt": "Fault is bracketed to the 45\u2013195 km segment (Campbelltown \u2192 Goulburn). Recommend a single dispatch \u2014 approve to proceed.",
                "option_1_title": "Send one engineer to the Goulburn splice site",
                "option_1_detail": "Action: dispatch Dave Mitchell (nearest on-call, ~12 min ETA) with an OTDR.\nWhy: per-sensor readings already localise the break to the 45\u2013195 km segment \u2014 one team can pinpoint and repair.\nRisk: minimal; if the break sits nearer Campbelltown, add ~25 min travel.",
                "option_2_title": "Send two teams to bracket from both ends",
                "option_2_detail": "Action: dispatch crews to Campbelltown and Albury simultaneously.\nWhy: marginally faster pinpoint if the fault location were unknown.\nRisk: doubles crew cost and pulls a second engineer off standby \u2014 unnecessary now the fault is already localised.",
                "recommended": 1,
            },
            "result": json.dumps({
                "type": "options",
                "prompt": "Fault is bracketed to the 45\u2013195 km segment (Campbelltown \u2192 Goulburn). Recommend a single dispatch \u2014 approve to proceed.",
                "options": [
                    {
                        "id": 1,
                        "title": "Send one engineer to the Goulburn splice site",
                        "detail": "Action: dispatch Dave Mitchell (nearest on-call, ~12 min ETA) with an OTDR.\nWhy: per-sensor readings already localise the break to the 45\u2013195 km segment \u2014 one team can pinpoint and repair.\nRisk: minimal; if the break sits nearer Campbelltown, add ~25 min travel.",
                        "recommended": True,
                    },
                    {
                        "id": 2,
                        "title": "Send two teams to bracket from both ends",
                        "detail": "Action: dispatch crews to Campbelltown and Albury simultaneously.\nWhy: marginally faster pinpoint if the fault location were unknown.\nRisk: doubles crew cost and pulls a second engineer off standby \u2014 unnecessary now the fault is already localised.",
                        "recommended": False,
                    },
                ],
            }),
            "duration_ms": 600,
        }
        approve_tc = {
            "id": "call_dispatch_approve",
            "name": "thinking",
            "arguments": {
                "thoughts": "Operator approved Option 1 \u2014 single dispatch to the Goulburn splice site. Proceeding with field dispatch and engineer call.",
            },
            "result": "Acknowledged.",
            "duration_ms": None,
        }
        otcs[idx:idx] = [options_tc, approve_tc]
        changed.append("orchestrator: +present_options +approval")

    # ── 3. Orchestrator content: severity rationale + dollars-saved ──────────
    anchor_sla = "exposure is contained to the two SYD\u2013MEL VPNs."
    if "classified **SEV-1** (a routine" not in orch["content"] and anchor_sla in orch["content"]:
        orch["content"] = orch["content"].replace(
            anchor_sla,
            anchor_sla
            + "\n- **Severity rationale:** multi-service blast radius + **$75,000/hr** live exposure \u21d2 classified **SEV-1** (a routine single-link event with no SLA impact would be SEV-3).",
            1,
        )
        changed.append("orchestrator: +severity rationale")

    if "## Financial Outcome" not in orch["content"] and "## Next Steps" in orch["content"]:
        orch["content"] = orch["content"].replace(
            "## Next Steps",
            "## Financial Outcome\n"
            "- **Reroute completed ~90 seconds after detection** \u2014 enterprise SLA exposure held to \u2248**$1,900** versus **$75,000/hour** had the corridor stayed down. Every minute of automated coordination is ~**$1,250** in penalties avoided.\n\n"
            "## Next Steps",
            1,
        )
        changed.append("orchestrator: +financial outcome")

    # ── 2. Comms: Work IQ stakeholder context ────────────────────────────────
    comms = _assistant(th["communicationsSpecialist"])
    ctcs = comms["tool_calls"]
    if not any(tc["id"] == "call_workiq_contacts" for tc in ctcs):
        workiq_tc = {
            "id": "call_workiq_contacts",
            "name": "ask_work_iq",
            "arguments": {
                "question": "Who should we notify at ACME and BigBank for an SLA-impacting outage, and is there prior context on this Sydney\u2013Melbourne corridor?",
            },
            "result": json.dumps({
                "status": "ok",
                "source_type": "Microsoft 365 \u2014 email + Teams",
                "match_confidence": 0.88,
                "response": (
                    "**From Microsoft 365 (Work IQ):**\n\n"
                    "- **Customer escalation contacts** \u2014 ACME Corporation: *Priya Naidoo, Network Operations Lead* (`acme-noc@acme.example`). BigBank Financial: *Tom Webster, Infrastructure Duty Manager* (`noc@bigbank.example`, 24\u00d77 desk).\n"
                    "- **Contractual clock (email, 3 weeks ago)** \u2014 \u201cSYD\u2013MEL latency excursion\u201d thread from *Hannah Cole (NOC Lead)*: ACME's contract requires customer notification within **15 minutes** of any SLA-affecting event.\n"
                    "- **Governance context (Teams \u00b7 NOC channel)** \u2014 a pinned note from the February infrastructure review flagged the **shared inland-conduit risk**; a diverse Brisbane path was approved but **not yet provisioned**."
                ),
            }),
            "duration_ms": 1400,
        }
        # Insert right after the opening 'thinking' so the order reads
        # think -> Work IQ context -> ticket -> advisory -> email.
        insert_at = 1 if ctcs and ctcs[0]["name"] == "thinking" else 0
        ctcs.insert(insert_at, workiq_tc)
        changed.append("comms: +ask_work_iq")

    if "Work IQ" not in comms["content"]:
        comms["content"] = (
            "Pulled stakeholder context from Microsoft 365 (Work IQ) \u2014 customer escalation contacts and ACME's 15-minute notification clock \u2014 then completed all three communications actions:\n"
            + comms["content"].split("\n", 1)[1]
            if comms["content"].startswith("All three communications actions completed:")
            else comms["content"]
        )
        changed.append("comms: +Work IQ note")

    REPLAY.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    if changed:
        print("Enhanced replay:")
        for c in changed:
            print("  -", c)
    else:
        print("No changes (already enhanced).")


if __name__ == "__main__":
    main()
