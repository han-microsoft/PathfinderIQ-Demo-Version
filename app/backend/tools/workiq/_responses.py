"""Canned M365 response catalog for the spoofed Work IQ tool.

Module role:
    Defines ``RESPONSE_CATALOG``: a list of dicts, each representing a
    plausible M365 data item (email, meeting, Teams message, document)
    that the spoofed ``ask_work_iq`` tool can return. Entries are curated
    to fit the telecom fibre-cut scenario narrative on the SYD-MEL
    corridor.

    Each entry has:
      - ``id``:          Unique identifier for logging/debugging.
      - ``source_type``: The M365 data source (email, meeting, teams, document, people).
      - ``keywords``:    Space-separated keywords for fuzzy matching.
      - ``response``:    The natural-language answer text returned to the agent.

Design rationale:
    Keywords are intentionally broad and overlapping so that the LLM's
    varied question phrasings still hit the right entry. The responses
    are written as if Copilot summarised real M365 items — complete with
    sender names, timestamps, subject lines, and quoted excerpts — to
    feel authentic in a live demo.

Dependents:
    Imported by: ``tools/workiq/_spoof.py`` (lazy import)
"""

from __future__ import annotations

# ── Response catalog ─────────────────────────────────────────────────────
# Each entry simulates a Work IQ response. Ordered roughly by expected
# demo query frequency (most likely questions first).

RESPONSE_CATALOG: list[dict] = [

    # ── People / escalation contacts (incident notification) ─────────────
    {
        "id": "people-customer-contacts",
        "source_type": "Microsoft 365 — email + Teams",
        "keywords": (
            "who notify contact contacts escalation customer ACME BigBank "
            "people stakeholder notification SLA impacting outage incident "
            "Priya Tom prior context corridor SYD-MEL sydney melbourne"
        ),
        "response": (
            "**From Microsoft 365 (Work IQ):**\n\n"
            "- **Customer escalation contacts** — ACME Corporation: *Priya Naidoo, "
            "Network Operations Lead* (`acme-noc@acme.example`). BigBank Financial: "
            "*Tom Webster, Infrastructure Duty Manager* (`noc@bigbank.example`, 24×7 desk).\n"
            "- **Contractual clock (email, 3 weeks ago)** — \"SYD–MEL latency excursion\" "
            "thread from *Hannah Cole (NOC Lead)*: ACME's contract requires customer "
            "notification within **15 minutes** of any SLA-affecting event.\n"
            "- **Governance context (Teams · NOC channel)** — a pinned note from the "
            "February infrastructure review flagged the **shared inland-conduit risk**; "
            "a diverse Brisbane path was approved but **not yet provisioned**."
        ),
    },

    # ── Emails ───────────────────────────────────────────────────────────

    {
        "id": "email-fibre-maintenance",
        "source_type": "email",
        "keywords": (
            "email fibre fiber corridor SYD-MEL sydney melbourne "
            "maintenance planned construction conduit goulburn "
            "infrastructure transport link cable"
        ),
        "response": (
            "I found 2 relevant emails:\n\n"
            "1. **From: Sarah Chen (Network Planning)** — 3 days ago\n"
            "   Subject: \"RE: SYD-MEL Fibre Route — Goulburn Construction Activity\"\n"
            "   > \"Heads up — council has approved a commercial development at the "
            "Goulburn interchange site. Construction starts next week. Our conduit runs "
            "within 15m of the excavation zone. I've flagged it with the contractor but "
            "we should consider a temporary reroute to the backup path via Canberra "
            "as a precaution.\"\n\n"
            "2. **From: James Liu (Transport Engineering)** — 1 week ago\n"
            "   Subject: \"SYD-MEL DWDM Trunk — Q1 Resilience Review\"\n"
            "   > \"Reminder that LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-FIBRE-02 share "
            "conduit COND-SYD-MEL-01 between Campbelltown and Goulburn. If we lose the "
            "primary, the backup is at shared risk. The tertiary via Brisbane is the only "
            "truly diverse path.\""
        ),
    },

    {
        "id": "email-sla-penalties",
        "source_type": "email",
        "keywords": (
            "email SLA penalty cost financial exposure enterprise "
            "ACME BigBank customer contract VPN breach service level "
            "agreement credit compensation"
        ),
        "response": (
            "I found 1 relevant email:\n\n"
            "**From: Rachel Nguyen (Commercial Operations)** — 2 weeks ago\n"
            "Subject: \"Updated SLA Penalty Rates — Enterprise VPN Contracts\"\n"
            "> \"Please note the updated penalty rates effective this quarter:\n"
            "> - ACME Corp (GOLD tier): $50,000/hr after 15-min grace period\n"
            "> - BigBank (SILVER tier): $25,000/hr after 30-min grace period\n"
            "> These are contractually binding. Any outage exceeding the grace period "
            "triggers automatic credits on the next invoice. Finance needs the RCA "
            "within 5 business days.\""
        ),
    },

    {
        "id": "email-outage-notification",
        "source_type": "email",
        "keywords": (
            "email outage alert incident notification down fault "
            "cut break disruption impacted services affected"
        ),
        "response": (
            "I found 1 relevant email from today:\n\n"
            "**From: NOC Automated Alerts <noc-alerts@optinet.com.au>** — 37 minutes ago\n"
            "Subject: \"[P1] Major Service Degradation — SYD-MEL Corridor\"\n"
            "> \"Multiple services reporting degradation on the Sydney-Melbourne corridor. "
            "20 correlated alerts received within 1-second window at 14:31:14 AEDT. "
            "Affected: 2 enterprise VPN tunnels, 3 residential broadband zones, "
            "3 mobile backhaul links. Preliminary assessment: transport-layer fault. "
            "NOC duty engineer notified. Severity: P1.\""
        ),
    },

    {
        "id": "email-field-engineer-update",
        "source_type": "email",
        "keywords": (
            "email field engineer dispatch repair truck OTDR "
            "splicer dave mitchell depot goulburn campbelltown equipment"
        ),
        "response": (
            "I found 1 relevant email:\n\n"
            "**From: Dave Mitchell (Regional Field Engineer)** — 2 hours ago\n"
            "Subject: \"RE: Equipment Check — Goulburn Depot\"\n"
            "> \"OTDR (Viavi T-BERD 4000) calibrated last week, ready to go. "
            "Fusion splicer (Fujikura 90S) has ~50 splices left on current electrodes. "
            "I'm on shift until 22:00 AEDT today. If dispatch comes through, I can be "
            "at the Goulburn interchange site in approximately 45 minutes from the depot.\""
        ),
    },

    # ── Calendar / Meetings ──────────────────────────────────────────────

    {
        "id": "meeting-resilience-review",
        "source_type": "meeting",
        "keywords": (
            "meeting calendar resilience review infrastructure upgrade "
            "fibre route diversity conduit risk SYD-MEL upcoming scheduled"
        ),
        "response": (
            "I found 2 upcoming meetings:\n\n"
            "1. **SYD-MEL Fibre Resilience Review** — Tomorrow, 10:00 AM AEDT\n"
            "   Organizer: James Liu (Transport Engineering)\n"
            "   Attendees: Sarah Chen, Mark Thompson, Rachel Nguyen, NOC Lead\n"
            "   Location: Teams (Bridge ID: 882-441-3309)\n"
            "   Notes: \"Review shared-risk conduit exposure between Campbelltown-Goulburn. "
            "Discuss tertiary path capacity via Brisbane. Budget approval for "
            "alternate conduit installation Q2.\"\n\n"
            "2. **Weekly NOC Standup** — Friday, 9:00 AM AEDT\n"
            "   Organizer: NOC Operations\n"
            "   Recurring — 30 minutes\n"
            "   Agenda includes: incident review, SLA breach summary, open P1/P2 tickets."
        ),
    },

    {
        "id": "meeting-postmortem",
        "source_type": "meeting",
        "keywords": (
            "meeting postmortem post-mortem RCA root cause review "
            "incident retrospective lessons learned previous prior"
        ),
        "response": (
            "I found 1 relevant past meeting:\n\n"
            "**SYD-MEL Fibre Cut — Post-Incident Review** — November 28, 2025\n"
            "Organizer: Mark Thompson (NOC Manager)\n"
            "Duration: 90 minutes\n"
            "Transcript excerpt:\n"
            "> Mark: \"The November 22 cut on the same Goulburn segment took 8.5 hours "
            "to resolve. The delay was primarily waiting for the OTDR — Campbelltown "
            "depot didn't have one calibrated.\"\n"
            "> Sarah: \"We've since moved a calibrated unit to Goulburn depot permanently. "
            "That should cut MTTR by at least 2 hours.\"\n"
            "> Action item: Procure second fusion splicer for Goulburn depot — assigned "
            "to Dave Mitchell, due Dec 15."
        ),
    },

    # ── Teams Messages ───────────────────────────────────────────────────

    {
        "id": "teams-noc-channel",
        "source_type": "teams",
        "keywords": (
            "teams messages channel NOC operations chat outage "
            "alert storm today incident fibre cut discussion"
        ),
        "response": (
            "Recent messages from the **#NOC-Operations** channel:\n\n"
            "**Mark Thompson** — 14:32 AEDT (today)\n"
            "> \"Seeing a burst of 20 alerts on SYD-MEL. All hit within 1 second. "
            "This looks like a transport-layer event, not application.\"\n\n"
            "**Sarah Chen** — 14:33 AEDT\n"
            "> \"Wasn't there construction near Goulburn this week? Check my email "
            "from 3 days ago — I flagged the conduit proximity risk.\"\n\n"
            "**Dave Mitchell** — 14:35 AEDT\n"
            "> \"I'm at Goulburn depot now. OTDR and splicer are ready. Waiting for "
            "dispatch confirmation. Can be on site in 45 min.\"\n\n"
            "**James Liu** — 14:38 AEDT\n"
            "> \"Confirmed: OPT-002 (Goulburn sensor) dropped to -32 dBm. OPT-001 "
            "(Campbelltown) is stable. The break is between these two points. "
            "Exactly the same pattern as the November incident.\""
        ),
    },

    {
        "id": "teams-enterprise-support",
        "source_type": "teams",
        "keywords": (
            "teams messages enterprise customer support ACME BigBank "
            "VPN complaint escalation account manager"
        ),
        "response": (
            "Recent messages from the **#Enterprise-Support** channel:\n\n"
            "**Lisa Park (Account Manager — ACME Corp)** — 14:40 AEDT\n"
            "> \"ACME's network team just called. Their VPN tunnel SVC-VPN-ACME went "
            "down at 14:31. They're asking for an ETA and whether this will trigger "
            "SLA penalties. Can someone from NOC give me talking points?\"\n\n"
            "**Tom Harris (Account Manager — BigBank)** — 14:42 AEDT\n"
            "> \"Same here — BigBank VPN is down. They have a batch processing window "
            "at 16:00 that requires the link. If we can't restore by then, they want "
            "to invoke the penalty clause.\""
        ),
    },

    # ── Documents ────────────────────────────────────────────────────────

    {
        "id": "doc-fibre-route-plan",
        "source_type": "document",
        "keywords": (
            "document documents file files sharepoint onedrive fibre route plan "
            "map conduit SYD-MEL path topology network design diagram pdf xlsx "
            "spreadsheet attachment shared risk assessment"
        ),
        "response": (
            "I found 2 relevant documents:\n\n"
            "1. **SYD-MEL_Fibre_Route_Plan_v3.2.pdf** — SharePoint > Network Engineering\n"
            "   Last modified by James Liu, 6 weeks ago\n"
            "   Summary: Detailed route plan for the Sydney-Melbourne DWDM trunk. "
            "Includes conduit mapping, splice point locations, sensor placement, "
            "and GPS coordinates for all access points along the corridor.\n\n"
            "2. **Shared_Risk_Conduit_Assessment_2025.xlsx** — SharePoint > Risk Management\n"
            "   Last modified by Sarah Chen, 3 weeks ago\n"
            "   Summary: Assessment of shared-risk conduit segments across all trunk "
            "routes. Flags COND-SYD-MEL-01 (Campbelltown-Goulburn) as HIGH RISK "
            "due to single-duct carrying both primary and backup fibres."
        ),
    },

    {
        "id": "doc-incident-procedures",
        "source_type": "document",
        "keywords": (
            "document procedures runbook playbook process SOP "
            "standard operating incident management response protocol"
        ),
        "response": (
            "I found 1 relevant document:\n\n"
            "**P1_Incident_Response_Playbook_v2.1.docx** — SharePoint > NOC Procedures\n"
            "Last modified by Mark Thompson, 2 months ago\n"
            "Summary: Standard operating procedures for P1 incidents. Key sections:\n"
            "- Section 3.2: Transport-layer fault triage (alert correlation + sensor "
            "  diagnostic sequence)\n"
            "- Section 4.1: SLA clock management (grace periods, notification timeline)\n"
            "- Section 5.3: Customer advisory templates for enterprise VPN outages\n"
            "- Section 6.1: Field dispatch protocol (equipment checklist, GPS coordinates, "
            "  depot inventory verification)"
        ),
    },

    # ── People ───────────────────────────────────────────────────────────

    {
        "id": "people-noc-team",
        "source_type": "people",
        "keywords": (
            "people person who team NOC operations staff duty roster "
            "engineer manager on-call shift contact responsible"
        ),
        "response": (
            "People working on NOC operations and the SYD-MEL corridor:\n\n"
            "- **Mark Thompson** — NOC Manager\n"
            "  Reports to: VP Network Operations\n"
            "  Recent activity: Organized SYD-MEL post-incident review (Nov 28)\n\n"
            "- **Sarah Chen** — Network Planning Engineer\n"
            "  Reports to: Director of Transport Engineering\n"
            "  Recent activity: Flagged Goulburn construction risk 3 days ago\n\n"
            "- **James Liu** — Transport Engineering Lead\n"
            "  Reports to: Director of Transport Engineering\n"
            "  Recent activity: Updated SYD-MEL fibre route plan, scheduled resilience review\n\n"
            "- **Dave Mitchell** — Regional Field Engineer (Goulburn region)\n"
            "  Reports to: Field Operations Manager\n"
            "  Recent activity: Confirmed depot equipment readiness, on shift until 22:00 AEDT"
        ),
    },

    {
        "id": "people-account-managers",
        "source_type": "people",
        "keywords": (
            "people person who account manager managers enterprise customer "
            "contact ACME BigBank relationship commercial sales responsible "
            "lisa park tom harris phone number"
        ),
        "response": (
            "Enterprise account managers for affected customers:\n\n"
            "- **Lisa Park** — Account Manager, ACME Corp\n"
            "  Phone: +61 2 9876 5432\n"
            "  Recent activity: Escalated ACME VPN outage enquiry at 14:40 AEDT today\n\n"
            "- **Tom Harris** — Account Manager, BigBank\n"
            "  Phone: +61 2 9876 5433\n"
            "  Recent activity: Escalated BigBank VPN concern and batch processing deadline"
        ),
    },

    # ── v3: Field engineer status updates ────────────────────────────────
    # These entries enable the "Any updates from the engineers?" demo step.
    # The orchestrator calls ask_work_iq to pull field status from Teams.

    {
        "id": "teams-karen-lee-field-update",
        "source_type": "teams",
        "keywords": (
            "teams messages field engineer update karen lee albury amplifier "
            "temperature power status site inspection report all clear "
            "AMP-SYD-MEL-ALBURY dispatch update engineer status"
        ),
        "response": (
            "Recent message from the **#NOC-Field-Ops** channel:\n\n"
            "**Karen Lee** — 16:05 AEDT (today)\n"
            "> \"On site at AMP-SYD-MEL-ALBURY. Amplifier site inspection complete. "
            "Findings:\n"
            "> - Mains power: NORMAL. MCB intact, no tripped breakers.\n"
            "> - UPS: Battery at 94%, no discharge events in log.\n"
            "> - EDFA status: All pump lasers operating within spec.\n"
            "> - Cabinet temperature: 38°C internal, 35°C ambient. "
            "Sun exposure on the west-facing cabinet panel — afternoon "
            "heat is the cause. No insulation damage. Recommend installing "
            "a sunshade panel on the west face (maintenance ticket raised).\n"
            "> - Optical power through amplifier: normal once upstream signal "
            "is restored.\n\n"
            "> **Verdict: Albury amplifier is NOT experiencing an independent "
            "failure. Temperature anomaly was solar heating. All clear. "
            "Returning to depot.**\""
        ),
    },

    {
        "id": "teams-dave-mitchell-otdr-update",
        "source_type": "teams",
        "keywords": (
            "teams messages field engineer update dave mitchell goulburn "
            "OTDR trace splice splicer fibre cut break repair confirmation "
            "fault location excavation damage conduit OPT-002 dispatch status"
        ),
        "response": (
            "Recent message from the **#NOC-Field-Ops** channel:\n\n"
            "**Dave Mitchell** — 15:52 AEDT (today)\n"
            "> \"On site at Goulburn interchange — splice point near OPT-002 sensor. "
            "OTDR trace complete. Results:\n"
            "> - Clean break confirmed at 197.3 km from Sydney headend "
            "(consistent with OPT-002 sensor location at 195 km ±3 km).\n"
            "> - Reflectance signature indicates a sharp cut, not a bend or crush.\n"
            "> - Visual inspection: excavation damage to conduit COND-SYD-MEL-01 "
            "approximately 200m south of the interchange overpass. Third-party "
            "construction crew hit the conduit with a backhoe. Conduit breached, "
            "fibre sheath torn. 4 of 48 fibres severed (our DWDM trunk pair "
            "included).\n"
            "> - Splicer situation: Campbelltown depot splicer is with Marcus Chen "
            "at AGG-SYD-SOUTH-01. Marcus is wrapping up — splicer will be "
            "couriered to me, ETA 90 minutes. Alternatively, Karen Lee at Albury "
            "has a splicer if her site checks out clear.\n\n"
            "> **Awaiting splicer arrival. Will begin splice prep (fibre "
            "stripping, cleaning, tray setup) in the meantime. Estimated "
            "splice completion: 2–3 hours after splicer arrives.**\""
        ),
    },
]
