#!/usr/bin/env python3
"""Patch the replay conversation JSON with improved demo flow.

Changes:
  NetworkInvestigator:
    A. Add query_graph: sensors on link
    B. Add query_telemetry: per-sensor optical readings
    C. Add query_graph: shared-risk conduit check
    D. Rewrite assistant content with fault localization + conduit warning

  KnowledgeAnalyst:
    E. Add search_tickets for SLA penalty numbers
    F. Add SLA penalty section to assistant content

  Orchestrator:
    G. Remove the broken present_options tool call
    H. Add dispatch_field_engineer tool call
    I. Add call_engineer tool call
    J. Add delegate_to_agent → communicationsSpecialist
    K. Rewrite assistant content with complete summary

  CommunicationsSpecialist:
    L. Add full thread with create_incident_ticket, update_advisory, send_incident_report
"""

import json
import sys
from pathlib import Path
from copy import deepcopy

SRC = Path(__file__).resolve().parent.parent / "public" / "replay-conversation.json"

def patch():
    with open(SRC) as f:
        conv = json.load(f)

    threads = conv["threads"]

    # ── NetworkInvestigator ──────────────────────────────────────────────────

    ni = threads["networkInvestigator"]
    ni_assistant = next(m for m in ni["messages"] if m["role"] == "assistant")

    # Insert new tool calls before the last existing tool call (the telemetry query)
    new_ni_tools = [
        {
            "id": "call_sensor_graph",
            "name": "query_graph",
            "arguments": {
                "query": "MATCH (s:Sensor)-[m:monitors_transportlink]->(tl:TransportLink)\nWHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'\nRETURN s.SensorId, s.SensorType, s.MountLocation, s.Latitude, s.Longitude"
            },
            "result": json.dumps({
                "columns": [
                    {"name": "s.SensorId", "type": "string"},
                    {"name": "s.SensorType", "type": "string"},
                    {"name": "s.MountLocation", "type": "string"},
                    {"name": "s.Latitude", "type": "number"},
                    {"name": "s.Longitude", "type": "number"},
                ],
                "data": [
                    {"s.SensorId": "SENS-SYD-MEL-F1-OPT-001", "s.SensorType": "OpticalPower", "s.MountLocation": "Splice point \u2014 45km south of Sydney CBD near Campbelltown", "s.Latitude": -34.065, "s.Longitude": 150.814},
                    {"s.SensorId": "SENS-SYD-MEL-F1-OPT-002", "s.SensorType": "OpticalPower", "s.MountLocation": "Splice point \u2014 Goulburn interchange (near AMP-SYD-MEL-GOULBURN)", "s.Latitude": -34.7546, "s.Longitude": 149.7186},
                    {"s.SensorId": "SENS-SYD-MEL-F1-OPT-003", "s.SensorType": "OpticalPower", "s.MountLocation": "Splice point \u2014 15km north of Albury (near AMP-SYD-MEL-ALBURY)", "s.Latitude": -36.0237, "s.Longitude": 146.912},
                    {"s.SensorId": "SENS-SYD-MEL-F1-BER-001", "s.SensorType": "BitErrorRate", "s.MountLocation": "Head-end transceiver bay \u2014 CORE-SYD-01 rack B3", "s.Latitude": -33.8688, "s.Longitude": 151.2093},
                    {"s.SensorId": "SENS-SYD-MEL-F1-BER-002", "s.SensorType": "BitErrorRate", "s.MountLocation": "Tail-end transceiver bay \u2014 CORE-MEL-01 rack A7", "s.Latitude": -37.8136, "s.Longitude": 144.9631},
                ]
            }),
            "duration_ms": 3200
        },
        {
            "id": "call_sensor_telemetry",
            "name": "thinking",
            "arguments": {
                "thoughts": "Have sensor locations; need per-sensor optical readings at incident time to triangulate fault between last-normal and first-LoL sensor."
            },
            "result": "Acknowledged.",
            "duration_ms": None
        },
        {
            "id": "call_sensor_readings",
            "name": "query_telemetry",
            "arguments": {
                "query": "SensorReadings\n| where SensorId startswith 'SENS-SYD-MEL-F1-OPT'\n| top 15 by Timestamp desc\n| project Timestamp, SensorId, SensorType, Value, Unit, Status"
            },
            "result": json.dumps({
                "columns": [
                    {"name": "Timestamp", "type": "datetime"},
                    {"name": "SensorId", "type": "string"},
                    {"name": "SensorType", "type": "string"},
                    {"name": "Value", "type": "real"},
                    {"name": "Unit", "type": "string"},
                    {"name": "Status", "type": "string"},
                ],
                "rows": [
                    {"Timestamp": "2026-02-06T14:31:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-001", "SensorType": "OpticalPower", "Value": -10.4, "Unit": "dBm", "Status": "NORMAL"},
                    {"Timestamp": "2026-02-06T14:31:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-002", "SensorType": "OpticalPower", "Value": -31.8, "Unit": "dBm", "Status": "CRITICAL"},
                    {"Timestamp": "2026-02-06T14:31:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-003", "SensorType": "OpticalPower", "Value": -32.1, "Unit": "dBm", "Status": "CRITICAL"},
                    {"Timestamp": "2026-02-06T14:26:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-001", "SensorType": "OpticalPower", "Value": -10.3, "Unit": "dBm", "Status": "NORMAL"},
                    {"Timestamp": "2026-02-06T14:26:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-002", "SensorType": "OpticalPower", "Value": -11.0, "Unit": "dBm", "Status": "NORMAL"},
                    {"Timestamp": "2026-02-06T14:26:18+00:00", "SensorId": "SENS-SYD-MEL-F1-OPT-003", "SensorType": "OpticalPower", "Value": -10.8, "Unit": "dBm", "Status": "NORMAL"},
                ]
            }),
            "duration_ms": 4800
        },
        {
            "id": "call_conduit_thinking",
            "name": "thinking",
            "arguments": {
                "thoughts": "Sensor data confirms fault between Campbelltown (45km, normal) and Goulburn (195km, LoL). Now need to check if backup fibre FIBRE-02 shares the same physical conduit \u2014 critical for diversity assessment."
            },
            "result": "Acknowledged.",
            "duration_ms": None
        },
        {
            "id": "call_conduit_check",
            "name": "query_graph",
            "arguments": {
                "query": "MATCH (tl:TransportLink)-[rt:routed_through]->(pc:PhysicalConduit)\nWHERE tl.LinkId IN ['LINK-SYD-MEL-FIBRE-01', 'LINK-SYD-MEL-FIBRE-02']\nRETURN tl.LinkId, pc.ConduitId, pc.RouteDescription, pc.MaterialType"
            },
            "result": json.dumps({
                "columns": [
                    {"name": "tl.LinkId", "type": "string"},
                    {"name": "pc.ConduitId", "type": "string"},
                    {"name": "pc.RouteDescription", "type": "string"},
                    {"name": "pc.MaterialType", "type": "string"},
                ],
                "data": [
                    {"tl.LinkId": "LINK-SYD-MEL-FIBRE-01", "pc.ConduitId": "CONDUIT-SYD-MEL-INLAND", "pc.RouteDescription": "Sydney to Melbourne via Hume Highway / Goulburn \u2014 inland route through Southern Highlands", "pc.MaterialType": "Underground Duct"},
                    {"tl.LinkId": "LINK-SYD-MEL-FIBRE-02", "pc.ConduitId": "CONDUIT-SYD-MEL-INLAND", "pc.RouteDescription": "Sydney to Melbourne via Hume Highway / Goulburn \u2014 inland route through Southern Highlands", "pc.MaterialType": "Underground Duct"},
                ]
            }),
            "duration_ms": 2100
        },
    ]

    # Append new tool calls
    ni_assistant["tool_calls"].extend(new_ni_tools)

    # Patch the assistant content to include fault localization and conduit warning
    ni_content_addition = """

---

### (5) Per-sensor fault localization (SensorReadings at incident time)
Optical power readings at the three corridor splice sensors at 14:31:18Z vs baseline (14:26:18Z):

| Sensor | Location | Baseline | At incident | Status |
|---|---|---|---|---|
| **SENS-SYD-MEL-F1-OPT-001** | Campbelltown (45km) | -10.3 dBm | **-10.4 dBm** | **NORMAL** \u2014 fault is downstream |
| **SENS-SYD-MEL-F1-OPT-002** | Goulburn (195km) | -11.0 dBm | **-31.8 dBm** | **CRITICAL \u2014 LOSS OF LIGHT** |
| **SENS-SYD-MEL-F1-OPT-003** | Albury (460km) | -10.8 dBm | **-32.1 dBm** | **CRITICAL \u2014 LOSS OF LIGHT** |

**Fault bracketed:** Between **Campbelltown** (45km, last normal) and **Goulburn** (195km, first LoL). Dispatch target: **GPS -34.7546, 149.7186** (Goulburn splice/AMP site).

---

### (6) Shared-risk conduit check (PhysicalConduit graph traversal)
Both SYD\u2013MEL fibres route through the **same physical conduit**:

| Link | Conduit | Route |
|---|---|---|
| LINK-SYD-MEL-FIBRE-01 | **CONDUIT-SYD-MEL-INLAND** | Hume Highway / Goulburn \u2014 inland route |
| LINK-SYD-MEL-FIBRE-02 | **CONDUIT-SYD-MEL-INLAND** | Hume Highway / Goulburn \u2014 inland route |

**\u26a0\ufe0f CRITICAL:** The backup fibre is **NOT physically diverse** \u2014 both share the same underground duct. If this is a dig strike or conduit damage, **FIBRE-02 may also fail**. The only truly diverse path is the **TERTIARY via Brisbane** (MPLS-PATH-SYD-MEL-VIA-BNE)."""

    ni_assistant["content"] += ni_content_addition

    # ── KnowledgeAnalyst ─────────────────────────────────────────────────────

    ka = threads["knowledgeAnalyst"]
    ka_assistant = next(m for m in ka["messages"] if m["role"] == "assistant")

    # The KnowledgeAnalyst already found the tickets with SLA info. 
    # Just add SLA penalty section to the content.
    ka_content_addition = """

---

### SLA Penalty Exposure (from historical precedent + SLAPolicy data)

| Service | Customer | SLA Tier | Penalty/Hour | Notes |
|---|---|---|---|---|
| VPN-ACME-CORP | ACME Corporation | GOLD | **$50,000/hr** | 99.99% availability, 15ms max latency |
| VPN-BIGBANK | BigBank Financial | GOLD | **$25,000/hr** | 99.99% availability, 15ms max latency |
| BB-BUNDLE-SYD-NORTH | Residential | STANDARD | N/A | Best-effort SLA |
| BB-BUNDLE-MEL-EAST | Residential | STANDARD | N/A | Best-effort SLA |

**Combined enterprise exposure: $75,000/hour** while VPN services are unreachable. Reroute to SECONDARY (FIBRE-02) restores reachability but latency must be verified against SLA thresholds. If rerouted via Brisbane TERTIARY, latency will exceed 15ms \u2014 triggers SLA notification requirement even with service restored."""

    ka_assistant["content"] += ka_content_addition

    # ── Orchestrator ─────────────────────────────────────────────────────────

    orch = threads["orchestrator"]
    orch_assistant = next(m for m in orch["messages"] if m["role"] == "assistant")
    orch_tools = orch_assistant["tool_calls"]

    # Remove the broken present_options tool call (last one, which errored)
    orch_tools[:] = [tc for tc in orch_tools if tc["name"] != "present_options"]

    # Add dispatch, call_engineer, and delegate to comms specialist
    new_orch_tools = [
        {
            "id": "call_dispatch_dave",
            "name": "dispatch_field_engineer",
            "arguments": {
                "engineer_name": "Dave Mitchell",
                "engineer_email": "dave.mitchell@austtelco.com.au",
                "engineer_phone": "+61-412-555-401",
                "incident_summary": "SYD\u2013MEL fibre cut: LINK-SYD-MEL-FIBRE-01 loss-of-light confirmed between Campbelltown (45km) and Goulburn (195km) via per-sensor localization. Suspect physical damage on CONDUIT-SYD-MEL-INLAND.",
                "destination_description": "Goulburn splice/interchange + AMP-SYD-MEL-GOULBURN inline EDFA cabinet (AMP-SYD-MEL-03). Access via fenced compound off Hume Hwy service road; gate code 4527.",
                "destination_latitude": -34.7546,
                "destination_longitude": 149.7186,
                "physical_signs_to_inspect": "Check EDFA cabinet alarms/power/UPS; inspect SC/APC connectors; verify optical levels both directions; check for water ingress, damaged patch leads, bent fibre, recent works; run OTDR from splice point.",
                "sensor_ids": "LINK-SYD-MEL-FIBRE-01",
                "urgency": "HIGH"
            },
            "result": json.dumps({
                "status": "dispatched",
                "dispatch_id": "DISPATCH-20260206-143145",
                "urgency": "HIGH",
                "engineer": {"name": "Dave Mitchell", "email": "dave.mitchell@austtelco.com.au", "phone": "+61-412-555-401"},
                "destination": "Goulburn splice/interchange + AMP-SYD-MEL-GOULBURN",
                "gps": {"latitude": -34.7546, "longitude": 149.7186}
            }),
            "duration_ms": 1250
        },
        {
            "id": "call_phone_dave",
            "name": "call_engineer",
            "arguments": {
                "engineer_name": "Dave Mitchell",
                "phone": "+61-412-555-401"
            },
            "result": json.dumps({
                "status": "connected",
                "engineer": "Dave Mitchell",
                "phone": "+61-412-555-401",
                "message": "Engineer acknowledged dispatch, ETA 12 minutes to Goulburn site"
            }),
            "duration_ms": 8500
        },
        {
            "id": "call_thinking_pre_comms",
            "name": "thinking",
            "arguments": {
                "thoughts": "Field dispatch confirmed. Now need to delegate to CommunicationsSpecialist for formal incident ticket, customer advisory, and stakeholder email."
            },
            "result": "Acknowledged.",
            "duration_ms": 215
        },
        {
            "id": "call_delegate_comms",
            "name": "delegate_to_agent",
            "arguments": {
                "agent_id": "communicationsSpecialist",
                "task": "Incident synthesis for formal communications. Root cause: physical-layer failure (loss-of-light / probable fibre cut) on LINK-SYD-MEL-FIBRE-01, fault bracketed between Campbelltown (45km) and Goulburn (195km) by per-sensor localization. Both SYD-MEL fibres share CONDUIT-SYD-MEL-INLAND (not diverse). Blast radius: VPN-ACME-CORP (CRITICAL, $50k/hr SLA), VPN-BIGBANK (CRITICAL, $25k/hr SLA), BB-BUNDLE-SYD-NORTH, BB-BUNDLE-MEL-EAST, MOB-5G-MEL-3011, MOB-5G-SYD-2041, MOB-5G-SYD-2042. Actions taken: (1) rerouted VPN traffic to MPLS-PATH-SYD-MEL-SECONDARY via FIBRE-02, (2) admin-down on FIBRE-01 to prevent flapping, (3) dispatched Dave Mitchell to Goulburn amp/splice site (ETA 12 min). Please: create SEV-1 incident ticket, publish customer advisory for VPN-ACME-CORP and VPN-BIGBANK, and email the stakeholder incident report."
            },
            "result": json.dumps({
                "agent_id": "communicationsSpecialist",
                "status": "complete",
                "response": "All three communications actions completed:\n1. **Incident ticket created**: INC-2026-0206-143200 (SEV-1)\n2. **Customer advisory published**: ADV-20260206-143215 for VPN-ACME-CORP and VPN-BIGBANK\n3. **Stakeholder report emailed**: Sent to noc-leads@austtelco.com.au",
                "duration_ms": 12400
            }),
            "duration_ms": 12650
        },
    ]

    orch_tools.extend(new_orch_tools)

    # Rewrite orchestrator content with complete summary
    orch_assistant["content"] = """A **confirmed fibre cut on LINK-SYD-MEL-FIBRE-01** between Campbelltown (45km) and Goulburn (195km) is causing corridor-wide service degradation across enterprise VPNs, broadband, and mobile backhaul.

## Summary
- **Root cause (high confidence):** Physical-layer loss-of-light on **LINK-SYD-MEL-FIBRE-01**, fault localized by per-sensor optical readings to the **45km\u2013195km segment** (between Campbelltown and Goulburn splice points).
- **Shared-risk warning:** FIBRE-01 and FIBRE-02 share **CONDUIT-SYD-MEL-INLAND** \u2014 backup is **not physically diverse**. If conduit damage, both fibres at risk.
- **SLA exposure:** VPN-ACME-CORP ($50,000/hr) + VPN-BIGBANK ($25,000/hr) = **$75,000/hr** combined penalty while unreachable.

## Affected Infrastructure
- **Transport:** LINK-SYD-MEL-FIBRE-01 (failed, admin-down), LINK-SYD-MEL-FIBRE-02 (active, carries rerouted traffic)
- **Enterprise VPNs:** VPN-ACME-CORP (CRITICAL), VPN-BIGBANK (CRITICAL) \u2014 rerouted to SECONDARY
- **Broadband:** BB-BUNDLE-SYD-NORTH, BB-BUNDLE-MEL-EAST
- **Mobile backhaul:** MOB-5G-MEL-3011, MOB-5G-SYD-2041, MOB-5G-SYD-2042

## Actions Taken
1. **Traffic rerouted** \u2192 `reroute_traffic(MPLS-PATH-SYD-MEL-SECONDARY)` \u2014 VPN traffic shifted to FIBRE-02
2. **Failed link stabilized** \u2192 `set_link_status(LINK-SYD-MEL-FIBRE-01, admin_down)` \u2014 prevents flap/reconvergence
3. **Field engineer dispatched** \u2192 `dispatch_field_engineer(Dave Mitchell)` \u2014 Goulburn amp/splice site, ETA 12 min
4. **Engineer contacted** \u2192 `call_engineer(Dave Mitchell)` \u2014 acknowledged, en route
5. **Incident ticket created** \u2192 INC-2026-0206-143200 (SEV-1)
6. **Customer advisory published** \u2192 ADV-20260206-143215 (VPN-ACME-CORP, VPN-BIGBANK)
7. **Stakeholder report emailed** \u2192 sent to NOC leads

## Next Steps
- Monitor FIBRE-02 utilization \u2014 currently viable at ~50% but if conduit is compromised, prepare **TERTIARY via Brisbane** (higher latency, triggers SLA notification)
- Dave Mitchell to run OTDR from Goulburn splice point to pinpoint exact break location
- If splice repair needed, Marcus Chen (Campbelltown) has Fujikura 90S splicer \u2014 stage as backup
- Karen Lee (Albury) on standby if fault brackets further south"""

    # ── CommunicationsSpecialist thread ──────────────────────────────────────

    comms_thread = {
        "agent_session_id": "ast_comms_replay_001",
        "agent_id": "communicationsSpecialist",
        "agent_name": "CommunicationsSpecialist",
        "messages": [
            {
                "id": "comms_sys_001",
                "role": "system",
                "content": "You are CommunicationsSpecialist. You handle all incident communications: formal tickets, customer advisories, and stakeholder reports.",
                "status": "complete",
                "tool_calls": [],
                "agent_name": "communicationsSpecialist",
                "context_snapshot": None,
                "created_at": "2026-03-04T19:23:55.088321+00:00"
            },
            {
                "id": "comms_user_001",
                "role": "user",
                "content": "Incident synthesis for formal communications. Root cause: physical-layer failure (loss-of-light / probable fibre cut) on LINK-SYD-MEL-FIBRE-01, fault bracketed between Campbelltown (45km) and Goulburn (195km) by per-sensor localization. Both SYD-MEL fibres share CONDUIT-SYD-MEL-INLAND (not diverse). Blast radius: VPN-ACME-CORP (CRITICAL, $50k/hr SLA), VPN-BIGBANK (CRITICAL, $25k/hr SLA), BB-BUNDLE-SYD-NORTH, BB-BUNDLE-MEL-EAST, MOB-5G-MEL-3011, MOB-5G-SYD-2041, MOB-5G-SYD-2042. Actions taken: (1) rerouted VPN traffic to MPLS-PATH-SYD-MEL-SECONDARY via FIBRE-02, (2) admin-down on FIBRE-01 to prevent flapping, (3) dispatched Dave Mitchell to Goulburn amp/splice site (ETA 12 min). Please: create SEV-1 incident ticket, publish customer advisory for VPN-ACME-CORP and VPN-BIGBANK, and email the stakeholder incident report.",
                "status": "complete",
                "tool_calls": [],
                "agent_name": "orchestrator",
                "context_snapshot": None,
                "created_at": "2026-03-04T19:31:00.000000+00:00"
            },
            {
                "id": "comms_assistant_001",
                "role": "assistant",
                "content": "All three communications actions completed:\n1. **Incident ticket created**: INC-2026-0206-143200 (SEV-1) \u2014 assigned to NOC with full blast radius and remediation status\n2. **Customer advisory published**: ADV-20260206-143215 \u2014 notifying VPN-ACME-CORP and VPN-BIGBANK operations teams of service impact, reroute action, and 30-minute update cadence\n3. **Stakeholder report emailed**: Sent to noc-leads@austtelco.com.au with root cause summary, SLA exposure ($75k/hr), remediation actions, and field dispatch status",
                "status": "complete",
                "tool_calls": [
                    {
                        "id": "call_comms_think1",
                        "name": "thinking",
                        "arguments": {
                            "thoughts": "Need to execute three communications actions in sequence: ticket first (establishes incident ID), then advisory (references ticket), then email report (references both)."
                        },
                        "result": "Acknowledged.",
                        "duration_ms": None
                    },
                    {
                        "id": "call_create_ticket",
                        "name": "create_incident_ticket",
                        "arguments": {
                            "severity": "SEV-1",
                            "title": "SYD\u2013MEL corridor fibre cut \u2014 LINK-SYD-MEL-FIBRE-01 loss-of-light causing multi-service impact",
                            "description": "Physical-layer failure on LINK-SYD-MEL-FIBRE-01. Fault localized between Campbelltown (45km) and Goulburn (195km) by per-sensor optical readings. Both SYD-MEL fibres share CONDUIT-SYD-MEL-INLAND (not diverse). Traffic rerouted to SECONDARY. Field engineer dispatched to Goulburn.",
                            "affected_services": "VPN-ACME-CORP,VPN-BIGBANK,BB-BUNDLE-SYD-NORTH,BB-BUNDLE-MEL-EAST,MOB-5G-MEL-3011,MOB-5G-SYD-2041,MOB-5G-SYD-2042",
                            "assigned_to": "NOC"
                        },
                        "result": json.dumps({
                            "ticket_id": "INC-2026-0206-143200",
                            "status": "open",
                            "severity": "SEV-1",
                            "title": "SYD\u2013MEL corridor fibre cut \u2014 LINK-SYD-MEL-FIBRE-01 loss-of-light causing multi-service impact",
                            "assigned_to": "NOC",
                            "url": "https://incidents.austtelco.internal/tickets/INC-2026-0206-143200"
                        }),
                        "duration_ms": 1850
                    },
                    {
                        "id": "call_advisory",
                        "name": "update_advisory",
                        "arguments": {
                            "message": "[P1 SERVICE IMPACT] SYD\u2013MEL corridor transport failure affecting VPN-ACME-CORP and VPN-BIGBANK. Root cause: physical fibre damage on intercity link. Traffic has been rerouted to backup path. Field team dispatched. Next update in 30 minutes. Ref: INC-2026-0206-143200."
                        },
                        "result": json.dumps({
                            "advisory_id": "ADV-20260206-143215",
                            "status": "posted",
                            "message": "Customer advisory posted for SYD-MEL corridor fibre cut"
                        }),
                        "duration_ms": 980
                    },
                    {
                        "id": "call_email_report",
                        "name": "send_incident_report",
                        "arguments": {
                            "recipients": "noc-leads@austtelco.com.au",
                            "subject": "[SEV-1] INC-2026-0206-143200 \u2014 SYD-MEL fibre cut \u2014 initial report",
                            "body": "Root cause: Loss-of-light on LINK-SYD-MEL-FIBRE-01, fault bracketed 45\u2013195km (Campbelltown\u2013Goulburn). Shared conduit risk: FIBRE-02 not diverse. SLA exposure: $75k/hr (ACME $50k + BigBank $25k). Actions: rerouted to SECONDARY, admin-down on FIBRE-01, Dave Mitchell dispatched to Goulburn (ETA 12 min). Advisory posted: ADV-20260206-143215."
                        },
                        "result": json.dumps({
                            "status": "sent",
                            "recipients": ["noc-leads@austtelco.com.au"],
                            "message_id": "MSG-20260206-143220"
                        }),
                        "duration_ms": 1200
                    },
                ],
                "agent_name": "communicationsSpecialist",
                "context_snapshot": None,
                "created_at": "2026-03-04T19:31:00.000000+00:00"
            }
        ],
        "created_at": "2026-03-04T19:23:55.088307Z"
    }

    threads["communicationsSpecialist"] = comms_thread

    # ── Write output ─────────────────────────────────────────────────────────

    with open(SRC, "w") as f:
        json.dump(conv, f, indent=2, ensure_ascii=False)

    print(f"Patched {SRC}")
    print(f"  NetworkInvestigator: +5 tool calls, +fault localization content")
    print(f"  KnowledgeAnalyst: +SLA penalty content")
    print(f"  Orchestrator: -present_options, +4 tool calls, rewritten summary")
    print(f"  CommunicationsSpecialist: new thread with 4 tool calls")

if __name__ == "__main__":
    patch()
