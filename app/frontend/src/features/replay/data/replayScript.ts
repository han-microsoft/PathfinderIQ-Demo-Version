/**
 * Replay script — pre-recorded NOC anomaly investigation session.
 *
 * Contains the full orchestrated sequence from agentouptutsdump.md
 * converted to ReplayStep[] for the replay engine. Token text is
 * chunked into small fragments to simulate streaming.
 *
 * Flow:
 *   1. Orchestrator: user message → thinking → delegate(networkInvestigator)
 *      → delegate(knowledgeAnalyst) → delegate(fieldCoordinator)
 *   2. networkInvestigator: delegation_start → error (failed in real run)
 *   3. knowledgeAnalyst: delegation_start → tools → tokens → done
 *   4. fieldCoordinator: delegation_start → tools → tokens → done
 *   5. Orchestrator: continues with create_incident_ticket, dispatch_field_engineer,
 *      call_engineer, update_advisory → final summary → done
 */

import type { ReplayStep, ReplayEvent } from "../types";

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Break text into word-boundary chunks to simulate token streaming. */
function tokenize(text: string, chunkSize = 3): string[] {
  const words = text.split(/(\s+)/);
  const chunks: string[] = [];
  let buf = "";
  for (const w of words) {
    buf += w;
    if (buf.split(/\s+/).filter(Boolean).length >= chunkSize) {
      chunks.push(buf);
      buf = "";
    }
  }
  if (buf) chunks.push(buf);
  return chunks;
}

/** Create token events with inter-token delays. */
function textTokens(text: string, tokenDelay = 30, chunkSize = 3): ReplayEvent[] {
  return tokenize(text, chunkSize).map((chunk) => ({
    delayMs: tokenDelay,
    eventType: "token",
    data: { token: chunk },
  }));
}

// ── User prompt (injected as a user message by the engine, not a delegation event) ──

export const USER_PROMPT = `[AUTOMATED TRIGGER — Fabric Eventhouse Anomaly Detector] An anomaly burst has been detected: 15 correlated alerts within 30 seconds on the SYD-MEL corridor. Mixed OPTICAL_DEGRADATION, HIGH_BER, and SERVICE_DEGRADATION alerts. Severity: mostly WARNING/MAJOR (no CRITICAL). Raw alert data below.

09:15:02.112 MAJOR LINK-SYD-MEL-FIBRE-01 OPTICAL_DEGRADATION Optical power degrading — approaching maintenance threshold
09:15:03.445 MAJOR LINK-SYD-MEL-FIBRE-01 HIGH_BER Bit error rate above acceptable threshold — link quality degrading
09:15:05.201 WARNING VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel quality degraded — increased jitter and packet loss
09:15:05.892 WARNING VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel quality degraded — latency spikes on primary MPLS path
09:15:07.334 WARNING MOB-5G-MEL-3011 SERVICE_DEGRADATION Backhaul degradation — intermittent voice quality drops
09:15:08.712 WARNING BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband quality degraded — upstream jitter
09:15:12.003 MAJOR LINK-SYD-MEL-FIBRE-01 OPTICAL_DEGRADATION Optical power continuing to degrade — now below -19 dBm
09:15:14.556 MAJOR VPN-ACME-CORP SERVICE_DEGRADATION VPN tunnel experiencing sustained packet loss above 4%
09:15:15.889 WARNING MOB-5G-SYD-2041 SERVICE_DEGRADATION Backhaul degradation — voice quality MOS dropping
09:15:18.223 MAJOR LINK-SYD-MEL-FIBRE-01 HIGH_BER Bit error rate accelerating — 7.2e-7 and rising
09:15:20.445 MAJOR VPN-BIGBANK SERVICE_DEGRADATION VPN tunnel latency exceeding 45ms — approaching SLA threshold
09:15:22.778 WARNING BB-BUNDLE-SYD-NORTH SERVICE_DEGRADATION Customer broadband quality degraded — bufferbloat
09:15:25.112 WARNING MOB-5G-SYD-2042 SERVICE_DEGRADATION Backhaul degradation — video call quality below threshold
09:15:28.334 WARNING LINK-SYD-MEL-FIBRE-01 CAPACITY_EXCEEDED Link utilization spiking as traffic fails over
09:15:31.667 MAJOR BB-BUNDLE-MEL-EAST SERVICE_DEGRADATION Customer broadband — sustained packet loss above 5%`;

// ── Orchestrator thinking ───────────────────────────────────────────────────

const ORCHESTRATOR_THINKING = `Correlated MAJOR/WARNING alarms indicate deteriorating optical conditions on LINK-SYD-MEL-FIBRE-01 (power drop, rising BER) causing multi-service degradation across VPN, mobile backhaul, and broadband; capacity spike suggests partial failover/congestion. Need immediate investigation of corridor telemetry/topology, check for protection switching, and pre-emptively prepare reroute and field dispatch if physical layer issue likely.`;

// ── Orchestrator final summary ──────────────────────────────────────────────

const ORCHESTRATOR_SUMMARY = `Degrading optical conditions on LINK-SYD-MEL-FIBRE-01 are driving widespread SYD–MEL service quality degradation (VPN/mobile backhaul/broadband), with indications of partial failover and congestion.

**Summary**
**Trigger:** 15 correlated alerts in 30s starting 09:15 on SYD–MEL corridor.
**Most likely fault domain** (current confidence: medium): Physical layer degradation on LINK-SYD-MEL-FIBRE-01 (optical power drop + rising BER), potentially at/near an inline amplifier or splice (Goulburn is a known shared-risk segment per historical precedent).

**Affected Infrastructure**
- Transport link: LINK-SYD-MEL-FIBRE-01
  - OPTICAL_DEGRADATION: power reported below -19 dBm
  - HIGH_BER: 7.2e-7 and rising
  - CAPACITY_EXCEEDED: utilization spiking (consistent with failover/traffic shift)
- Impacted services (from alerts):
  - VPN-ACME-CORP, VPN-BIGBANK
  - MOB-5G-MEL-3011, MOB-5G-SYD-2041, MOB-5G-SYD-2042
  - BB-BUNDLE-MEL-EAST, BB-BUNDLE-SYD-NORTH

**Actions Taken (with tool references)**
1. **Opened incident ticket (SEV-2)**
   Tool: create_incident_ticket → INC-2026-0228-210928
2. **Dispatched field engineer to highest-likelihood site (Goulburn inline amp/splice)**
   Tool: dispatch_field_engineer → DISPATCH-20260228-210936
   Engineer: Dave Mitchell to AMP-SYD-MEL-GOULBURN / splice site (gate code 4527)
3. **Attempted direct phone contact with dispatched engineer**
   Tool: call_engineer → no_answer
4. **Posted customer advisory** (degraded performance notice)
   Tool: update_advisory → ADV-20260228-210948
5. **Runbook + precedent review completed** (procedural guidance + shared-risk warning near Goulburn; reroute permitted if alternate path <80% util).
   Source: knowledgeAnalyst delegation result
6. **Network investigation delegation failed** due to tool error
   Tool: delegate_to_agent(networkInvestigator, ...) → error (needs retry)

**Current Status**
Incident state: Active, not yet mitigated (no reroute executed yet; field dispatch in progress).
Customer impact: Performance degradation (latency/jitter/packet loss), severity WARNING/MAJOR, no CRITICAL reported in trigger.

**Next Steps (recommended)**
1. **Retry NetworkInvestigator** telemetry/topology pull immediately to confirm optical levels/OSNR/FEC/BER trend both ends, and whether protection switching is occurring.
2. If degradation persists or worsens: **execute pre-emptive MPLS reroute** to a backup path (gated by capacity <80%) per TE runbook.
3. If failover is already occurring and causing CAPACITY_EXCEEDED: reroute/traffic-engineer to a higher-capacity alternate (potentially indirect corridor) to stabilize SLAs.
4. **Follow up with Dave Mitchell** as he arrives onsite; if EDFA module fault suspected, expedite spare S40i (field coordinator flagged spare availability as unconfirmed).

**Status: Open SEV-2, field resources en route, advisory posted; immediate priority is to re-run network telemetry to decide on reroute.**`;

// ── Knowledge Analyst response ──────────────────────────────────────────────

const KNOWLEDGE_ANALYST_RESPONSE = `I'm KnowledgeAnalyst. Below are the most relevant SOPs and precedents for OPTICAL_DEGRADATION + HIGH_BER on long-haul fibre (SYD–MEL corridor), including when to trigger MPLS protection/reroute.

**Applicable Procedures**
**1) Optical degradation / rising BER triage & transport response**
- **Confirm it's degradation** (not Loss-of-Light / hard down)
  Check trend vs step-change in optical power and BER to classify gradual vs sudden degradation.
  Source: "Optical Amplifier Maintenance and Degradation Response" (amplifier_maintenance.md)
- **Map the link to inline sites** and isolate the likely segment
  Source: amplifier_maintenance.md, Procedure step 1
- **Check amplifier calibration recency**
  > 6 months since calibration + ongoing power drop ⇒ high priority recalibration
  > 12 months since calibration ⇒ critical immediate scheduling
- **Decision: amplifier ageing vs fibre/splice degradation**
  If degradation is gradual → maintenance/recalibration. If sudden → investigate fibre event/splice degradation.
- **Escalation trigger**: If degradation rate indicates potential failure within 7 days → pre-emptive traffic reroute + emergency field dispatch.

**2) When to trigger MPLS reroute / protection actions**
- **Prerequisite checks**: Confirm root cause category; ensure a SECONDARY MPLSPath exists.
- **Trigger criteria**: For hard failures → immediate reroute. For degradation → pre-emptive reroute if failure within 7 days.
- **Capacity gating**: Only reroute if alternate path utilisation after shift remains < 80%.
- **Execution**: Prefer automated make-before-break reroute; validate post-move.

**3) Corridor risk: shared-risk/conduit coupling (SYD–MEL)**
- FIBRE-01 and FIBRE-02 are co-routed near Goulburn — NOT physically diverse.
  Source: conduit_shared_risk_assessment.md

**Historical Precedent**
| Ticket ID | Date | Root cause | Time to reroute | MTTR |
|---|---|---|---|---|
| INC-2025-08-14-0042 | 2025-08-14 | FIBRE_CUT (contractor) | 45s | ~6 hours |
| INC-2025-11-22-0055 | 2025-11-22 | FIBRE_CUT (storm, dual impact) | 180s | ~18 hours |
| INC-2026-01-15-0021 | 2026-01-15 | CAPACITY_EXHAUSTION | N/A | ~2 hours |
| INC-2025-09-02-0018 | MEL–BNE | AMPLIFIER_FAILURE (EDFA) | — | ~4 hours |

**Typical root causes & ETR heuristics:**
- Physical fibre damage: ETR 6–18 hours on SYD–MEL corridor.
- Shared-risk segment near Goulburn: "backup" may fail in the same event.
- Amplifier/EDFA failure after degradation: field swap ETR ~4 hours.
- Reroute timing: 45–180 seconds when alternate capacity exists.`;

// ── Knowledge Analyst tool results (search_runbooks, search_tickets) ────────

const SEARCH_RUNBOOKS_RESULT_1 = JSON.stringify({
  results: [
    { document: "amplifier_maintenance.md", score: 0.03, title: "Optical Amplifier Maintenance and Degradation Response" },
    { document: "customer_communication_template.md", score: 0.03, title: "Customer Communication Template" },
    { document: "fibre_cut_runbook.md", score: 0.03, title: "Fibre Cut — Detection, Verification, and Recovery" },
    { document: "conduit_shared_risk_assessment.md", score: 0.03, title: "Conduit Shared Risk Group Assessment" },
    { document: "alert_storm_triage_guide.md", score: 0.03, title: "Alert Storm Triage Guide" },
  ],
});

const SEARCH_RUNBOOKS_RESULT_2 = JSON.stringify({
  results: [
    { document: "amplifier_maintenance.md", score: 0.03, title: "Optical Amplifier Maintenance and Degradation Response" },
    { document: "traffic_engineering_reroute.md", score: 0.03, title: "MPLS Traffic Engineering Reroute" },
    { document: "fibre_cut_runbook.md", score: 0.03, title: "Fibre Cut — Detection, Verification, and Recovery" },
    { document: "alert_storm_triage_guide.md", score: 0.01, title: "Alert Storm Triage Guide" },
  ],
});

const SEARCH_TICKETS_RESULT_1 = JSON.stringify({
  results: [
    { ticket: "INC-2025-11-22-0055", title: "Fibre cut SYD-MEL corridor - storm damage", severity: "P1", root_cause_type: "FIBRE_CUT" },
    { ticket: "INC-2025-09-02-0018", title: "DWDM amplifier failure MEL-BNE link", severity: "P1", root_cause_type: "AMPLIFIER_FAILURE" },
    { ticket: "INC-2025-08-14-0042", title: "Fibre cut SYD-MEL corridor - contractor damage", severity: "P1", root_cause_type: "FIBRE_CUT" },
    { ticket: "INC-2026-01-15-0021", title: "Capacity exhaustion LINK-SYD-MEL-FIBRE-02", severity: "P2", root_cause_type: "CAPACITY_EXHAUSTION" },
    { ticket: "INC-2026-02-01-0015", title: "Scheduled fibre maintenance SYD-BNE", severity: "P3", root_cause_type: "PLANNED_MAINTENANCE" },
  ],
});

const SEARCH_TICKETS_RESULT_2 = JSON.stringify({
  results: [
    { ticket: "INC-2025-09-02-0018", title: "DWDM amplifier failure MEL-BNE link", severity: "P1", root_cause_type: "AMPLIFIER_FAILURE" },
    { ticket: "INC-2025-11-22-0055", title: "Fibre cut SYD-MEL corridor - storm damage", severity: "P1", root_cause_type: "FIBRE_CUT" },
    { ticket: "INC-2025-08-14-0042", title: "Fibre cut SYD-MEL corridor - contractor damage", severity: "P1", root_cause_type: "FIBRE_CUT" },
    { ticket: "INC-2026-01-15-0021", title: "Capacity exhaustion LINK-SYD-MEL-FIBRE-02", severity: "P2", root_cause_type: "CAPACITY_EXHAUSTION" },
  ],
});

// ── Field Coordinator tool results (query_graph, search_infra_specs, search_equipment) ──

const FC_QUERY_GRAPH_LINK = JSON.stringify({
  columns: ["tl.LinkId", "tl.LinkType", "tl.CapacityGbps", "tl.SourceRouterId", "tl.TargetRouterId"],
  rows: [["LINK-SYD-MEL-FIBRE-01", "DWDM_100G", 100, "CORE-SYD-01", "CORE-MEL-01"]],
});

const FC_QUERY_GRAPH_AMPS = JSON.stringify({
  columns: ["a.SiteId", "a.Location", "a.InstalledYear", "a.LastCalibration", "a.Latitude", "a.Longitude"],
  rows: [
    ["AMP-SYD-MEL-GOULBURN", "Goulburn NSW — 195km from Sydney", 2018, "2025-09-15", -34.7546, 149.7186],
    ["AMP-SYD-MEL-ALBURY", "Albury NSW — 460km from Sydney", 2018, "2025-06-20", -36.0737, 146.9135],
  ],
});

const FC_QUERY_GRAPH_CONDUIT = JSON.stringify({
  columns: ["pc.ConduitId", "pc.RouteDescription", "pc.MaterialType", "pc.InstalledYear"],
  rows: [["CONDUIT-SYD-MEL-INLAND", "Sydney to Melbourne via Hume Highway / Goulburn — inland route through Southern Highlands", "Underground Duct", 2018]],
});

const FC_QUERY_GRAPH_SENSORS = JSON.stringify({
  columns: ["s.SensorId", "s.SensorType", "s.MountLocation", "s.Latitude", "s.Longitude", "s.Status"],
  rows: [
    ["SENS-SYD-MEL-F1-BER-002", "BitErrorRate", "Tail-end transceiver bay — CORE-MEL-01 rack A7", -37.8136, 144.9631, "ACTIVE"],
    ["SENS-SYD-MEL-F1-OPT-001", "OpticalPower", "Splice point — 45km south of Sydney CBD near Campbelltown", -34.0650, 150.8140, "ACTIVE"],
    ["SENS-SYD-MEL-F1-BER-001", "BitErrorRate", "Head-end transceiver bay — CORE-SYD-01 rack B3", -33.8688, 151.2093, "ACTIVE"],
    ["SENS-SYD-MEL-F1-OPT-002", "OpticalPower", "Splice point — Goulburn interchange (near AMP-SYD-MEL-GOULBURN)", -34.7546, 149.7186, "ACTIVE"],
    ["SENS-SYD-MEL-F1-OPT-003", "OpticalPower", "Splice point — 15km north of Albury (near AMP-SYD-MEL-ALBURY)", -36.0237, 146.9120, "ACTIVE"],
  ],
});

const FC_QUERY_GRAPH_DEPOT_GOULBURN = JSON.stringify({
  columns: ["d.DepotId", "d.DepotName", "d.DepotType", "d.City", "d.Region"],
  rows: [["DEPOT-GOULBURN", "Goulburn Regional Depot", "RegionalDepot", "Goulburn", "NSW"]],
});

const FC_QUERY_GRAPH_DEPOT_ALBURY = JSON.stringify({
  columns: ["d.DepotId", "d.DepotName", "d.DepotType", "d.City", "d.Region"],
  rows: [["DEPOT-ALBURY", "Albury Regional Depot", "RegionalDepot", "Albury", "NSW"]],
});

const FC_QUERY_GRAPH_DEPOT_SYD = JSON.stringify({
  columns: ["d.DepotId", "d.DepotName", "d.DepotType", "d.City", "d.Region"],
  rows: [["DEPOT-SYD-CAMPBELLTOWN", "Campbelltown Depot", "CityHub", "Sydney", "NSW"]],
});

const FC_QUERY_GRAPH_DEPOT_MEL = JSON.stringify({
  columns: ["d.DepotId", "d.DepotName", "d.DepotType", "d.City", "d.Region"],
  rows: [["DEPOT-MEL-CLAYTON", "Clayton Depot", "CityHub", "Melbourne", "VIC"]],
});

const FC_QUERY_GRAPH_ROSTER_GOULBURN = JSON.stringify({
  columns: ["dr.PersonName", "dr.Email", "dr.Phone", "dr.Role", "dr.ShiftStart", "dr.ShiftEnd", "dr.VehicleId"],
  rows: [["Dave Mitchell", "dave.mitchell@austtelco.com.au", "+61-412-555-401", "RegionalFieldEngineer", "06:00", "18:00", "VEH-REG-02"]],
});

const FC_QUERY_GRAPH_ROSTER_SYD = JSON.stringify({
  columns: ["dr.PersonName", "dr.Email", "dr.Phone", "dr.Role", "dr.ShiftStart", "dr.ShiftEnd", "dr.VehicleId"],
  rows: [
    ["Sarah O'Brien", "sarah.obrien@austtelco.com.au", "+61-412-555-102", "FieldEngineer", "18:00", "06:00", "VEH-SYD-07"],
    ["Marcus Chen", "marcus.chen@austtelco.com.au", "+61-412-555-101", "FieldEngineer", "06:00", "18:00", "VEH-SYD-03"],
  ],
});

const FC_QUERY_GRAPH_ROSTER_ALBURY = JSON.stringify({
  columns: ["dr.PersonName", "dr.Email", "dr.Phone", "dr.Role", "dr.ShiftStart", "dr.ShiftEnd", "dr.VehicleId"],
  rows: [["Karen Lee", "karen.lee@austtelco.com.au", "+61-412-555-402", "RegionalFieldEngineer", "06:00", "18:00", "VEH-REG-04"]],
});

const FC_QUERY_GRAPH_ROSTER_MEL = JSON.stringify({
  columns: ["dr.PersonName", "dr.Email", "dr.Phone", "dr.Role", "dr.ShiftStart", "dr.ShiftEnd", "dr.VehicleId"],
  rows: [
    ["James Nguyen", "james.nguyen@austtelco.com.au", "+61-412-555-201", "FieldEngineer", "06:00", "18:00", "VEH-MEL-02"],
    ["Priya Sharma", "priya.sharma@austtelco.com.au", "+61-412-555-202", "FieldEngineer", "18:00", "06:00", "VEH-MEL-05"],
  ],
});

const FC_SEARCH_INFRA = JSON.stringify({
  results: [
    { document: "AMP-SYD-MEL-03-site-spec.md", title: "Site Specification — AMP-SYD-MEL-03 (Goulburn)", site_id: "AMP-SYD-MEL-03", access_code: "4527" },
  ],
});

const FC_SEARCH_EQUIP_1 = JSON.stringify({
  results: [
    { document: "DEPOT-SYD-CAMPBELLTOWN-manifest.md", items: ["Viavi T-BERD 4000 — Available", "Fujikura 90S — Available", "EXFO FPM-300 — Available"] },
    { document: "DEPOT-MEL-CLAYTON-manifest.md", items: ["Viavi T-BERD 4000 — Available", "Fujikura 90S — Available", "EXFO FPM-300 — Available"] },
  ],
});

const FC_SEARCH_EQUIP_2 = JSON.stringify({
  results: [
    { document: "DEPOT-SYD-CAMPBELLTOWN-manifest.md", note: "No EDFA spare module found in manifest" },
    { document: "DEPOT-MEL-CLAYTON-manifest.md", note: "No EDFA spare module found in manifest" },
  ],
});

const FC_SEARCH_EQUIP_3 = JSON.stringify({
  results: [
    { note: "Lumentum S40i spare not confirmed at any depot — escalation required to central spares" },
  ],
});

// ── Field Coordinator response text ─────────────────────────────────────────

const FIELD_COORDINATOR_RESPONSE = `I'm FieldCoordinator. Below is the dispatch prep package for LINK-SYD-MEL-FIBRE-01 (DWDM_100G) optical degradation / high BER on the SYD–MEL inland conduit (Hume Hwy / Goulburn shared-risk segment).
Sources: graph topology/sensors/rosters (query_graph), site spec (search_infra_specs), depot manifests (search_equipment).

**Likely physical fault sites to target (ranked; SYD→MEL)**
| Priority | Site / Entity | What it is | Why it's relevant |
|---|---|---|---|
| 1 | Goulburn splice/interchange + AMP-SYD-MEL-GOULBURN | Inline EDFA cabinet + splice tray | Shared-risk segment; primary corridor amplifier site |
| 2 | Campbelltown splice point | Field splice point | Optical power sensor south of Sydney |
| 3 | AMP-SYD-MEL-ALBURY + nearby splice point | Inline EDFA cabinet + splice point | Second inline amp on this link |
| 4 | CORE-SYD-01 transceiver bay | Router optics/patching | BER sensor at Sydney head-end |
| 5 | CORE-MEL-01 transceiver bay | Router optics/patching | BER sensor at Melbourne tail-end |

**Site access notes (Goulburn amp cabinet)**
- Site: AMP-SYD-MEL-03 (Goulburn), Gate code: **4527**
- Access: Locked fenced compound off Hume Hwy service road; 24/7 accessible
- Power: 240V 15A mains + UPS (~45 min); 15A generator inlet available
- EDFA module type: Lumentum S40i (line EDFA)

**Primary dispatch recommendation**
| Engineer | Depot | ETA | Contact |
|---|---|---|---|
| Dave Mitchell (VEH-REG-02) | Goulburn Regional Depot | ~0–15 min | dave.mitchell@austtelco.com.au / +61-412-555-401 |
| Marcus Chen (VEH-SYD-03) | Campbelltown Depot | ~55 min to Goulburn | marcus.chen@austtelco.com.au / +61-412-555-101 |
| James Nguyen (VEH-MEL-02) | Clayton Depot | ~30–45 min (metro) | james.nguyen@austtelco.com.au / +61-412-555-201 |

**Critical blockers**
- EDFA spare module (Lumentum S40i): **Not confirmed** in depot manifests — escalate to logistics
- SFP/QSFP 100G optics spares: **Not confirmed** — confirm exact optic type and locate spares

**Suggested dispatch plan**
1. Stage Dave Mitchell to Goulburn splice/amp site for immediate inspection
2. Stage Marcus Chen with OTDR + cleaning + power meter to cover Campbelltown splice
3. Stage James Nguyen to CORE-MEL-01 transceiver bay
4. **Logistics escalation now**: locate Lumentum S40i EDFA spare + 100G optics spares`;

// ── Orchestrator tool call results ──────────────────────────────────────────

const CREATE_INCIDENT_RESULT = JSON.stringify({
  ticket_id: "INC-2026-0228-210928",
  status: "open",
  severity: "SEV-2",
  title: "SYD–MEL corridor degradation — LINK-SYD-MEL-FIBRE-01 optical power drop + high BER causing multi-service impact",
  assigned_to: "NOC",
  url: "https://incidents.austtelco.internal/tickets/INC-2026-0228-210928",
});

const DISPATCH_RESULT = JSON.stringify({
  status: "dispatched",
  dispatch_id: "DISPATCH-20260228-210936",
  urgency: "HIGH",
  engineer: { name: "Dave Mitchell", email: "dave.mitchell@austtelco.com.au", phone: "+61-412-555-401" },
  destination: "Goulburn splice/interchange + AMP-SYD-MEL-GOULBURN inline EDFA cabinet (AMP-SYD-MEL-03). Access via fenced compound off Hume Hwy service road; gate code 4527.",
  gps: { latitude: -34.7546, longitude: 149.7186 },
  sensors: ["LINK-SYD-MEL-FIBRE-01"],
});

const CALL_ENGINEER_RESULT = JSON.stringify({
  status: "no_answer",
  engineer: "Dave Mitchell",
  phone: "+61-412-555-401",
  message: "Recipient didn't pick up",
});

const UPDATE_ADVISORY_RESULT = JSON.stringify({
  advisory_id: "ADV-20260228-210948",
  status: "posted",
  message: "Customer advisory posted for SYD-MEL corridor degradation",
});

// ── Build the full replay script ────────────────────────────────────────────

export const REPLAY_SCRIPT: ReplayStep[] = [
  // ─── Step 1: Orchestrator — thinking + delegation tool calls ────────────
  {
    agentId: "orchestrator",
    switchTab: true,
    events: [
      { delayMs: 500, eventType: "delegation_start", data: {} },
      // Thinking
      { delayMs: 300, eventType: "thinking", data: { token: "" } },
      ...textTokens(ORCHESTRATOR_THINKING, 25, 4),
      // delegate_to_agent → networkInvestigator
      { delayMs: 600, eventType: "tool_call_start", data: { id: "tc_del_ni", name: "delegate_to_agent" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_del_ni", arguments: { agent_id: "networkInvestigator", task: "Investigate anomaly on SYD-MEL corridor affecting LINK-SYD-MEL-FIBRE-01. Pull latest telemetry: optical RX/TX power, OSNR, BER trend, FEC counters, alarms at both ends, protection switching status, utilization, and impacted services/routes. Identify available alternate links/paths and any auto-failover already occurring; recommend immediate mitigation (MPLS backup path IDs if applicable)." } } },
      // delegate_to_agent → knowledgeAnalyst
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_del_ka", name: "delegate_to_agent" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_del_ka", arguments: { agent_id: "knowledgeAnalyst", task: "Retrieve runbooks/procedures for OPTICAL_DEGRADATION + HIGH_BER on long-haul fibre (SYD-MEL corridor) and guidance for when to trigger MPLS reroute/protection actions. Also check historical tickets for LINK-SYD-MEL-FIBRE-01 or similar events (power below -19 dBm, BER ~1e-6) and typical root causes/ETR." } } },
      // delegate_to_agent → fieldCoordinator
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_del_fc", name: "delegate_to_agent" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_del_fc", arguments: { agent_id: "fieldCoordinator", task: "Prepare for potential dispatch related to LINK-SYD-MEL-FIBRE-01 optical degradation/high BER on SYD-MEL corridor. Identify nearest on-duty field engineer(s) and likely physical sites (inline amps/splice points) associated with SYD-MEL fibre, especially near shared-risk Goulburn segment. Provide engineer contact details, ETA, and required spares (EDFA module, SFP/QSFP optics, OTDR, cleaning kit)." } } },
    ],
  },

  // ─── Step 2: NetworkInvestigator — short successful response ───────────
  {
    agentId: "networkInvestigator",
    switchTab: true,
    events: [
      { delayMs: 1000, eventType: "delegation_start", data: {} },
      ...textTokens(
        "Telemetry indicates deteriorating optical conditions on LINK-SYD-MEL-FIBRE-01 with RX power trending below threshold and BER rising. Recommend immediate traffic protection/reroute while field verification is prepared.",
        22,
        4,
      ),
      { delayMs: 200, eventType: "done", data: {} },
    ],
  },

  // ─── Step 3: KnowledgeAnalyst — search tools + response ─────────────────
  {
    agentId: "knowledgeAnalyst",
    switchTab: true,
    events: [
      { delayMs: 500, eventType: "delegation_start", data: {} },
      // search_runbooks #1
      { delayMs: 400, eventType: "tool_call_start", data: { id: "tc_ka_sr1", name: "search_runbooks" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_ka_sr1", arguments: { query: "OPTICAL_DEGRADATION HIGH_BER long-haul fibre troubleshooting SYD MEL corridor power below -19 dBm BER 1e-6" } } },
      { delayMs: 1500, eventType: "tool_result", data: { id: "tc_ka_sr1", name: "search_runbooks", result: SEARCH_RUNBOOKS_RESULT_1 } },
      // search_runbooks #2
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_ka_sr2", name: "search_runbooks" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_ka_sr2", arguments: { query: "MPLS reroute protection trigger criteria optical degradation high BER threshold" } } },
      { delayMs: 1200, eventType: "tool_result", data: { id: "tc_ka_sr2", name: "search_runbooks", result: SEARCH_RUNBOOKS_RESULT_2 } },
      // search_tickets #1
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_ka_st1", name: "search_tickets" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_ka_st1", arguments: { query: "LINK-SYD-MEL-FIBRE-01 optical degradation power -19 dBm BER 1e-6" } } },
      { delayMs: 1500, eventType: "tool_result", data: { id: "tc_ka_st1", name: "search_tickets", result: SEARCH_TICKETS_RESULT_1 } },
      // search_tickets #2
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_ka_st2", name: "search_tickets" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_ka_st2", arguments: { query: "optical power -19 dBm high BER 1e-6 SYD-MEL degradation" } } },
      { delayMs: 1200, eventType: "tool_result", data: { id: "tc_ka_st2", name: "search_tickets", result: SEARCH_TICKETS_RESULT_2 } },
      // Thinking
      { delayMs: 300, eventType: "thinking", data: { token: "" } },
      ...textTokens("I've pulled runbooks covering optical amplifier degradation response and MPLS TE reroute criteria, plus related fibre-cut and SRG assessment guidance. Next, I'll summarise actionable steps.", 25, 4),
      // Response tokens
      ...textTokens(KNOWLEDGE_ANALYST_RESPONSE, 20, 4),
      // Done
      { delayMs: 200, eventType: "done", data: {} },
    ],
  },

  // ─── Step 4: FieldCoordinator — many graph queries + response ───────────
  {
    agentId: "fieldCoordinator",
    switchTab: true,
    events: [
      { delayMs: 500, eventType: "delegation_start", data: {} },
      // query_graph: link info
      { delayMs: 400, eventType: "tool_call_start", data: { id: "tc_fc_q1", name: "query_graph" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_q1", arguments: { query: "MATCH (tl:TransportLink) WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN tl.LinkId, tl.LinkType, tl.CapacityGbps, tl.SourceRouterId, tl.TargetRouterId" } } },
      { delayMs: 800, eventType: "tool_result", data: { id: "tc_fc_q1", name: "query_graph", result: FC_QUERY_GRAPH_LINK } },
      // Thinking
      { delayMs: 200, eventType: "thinking", data: { token: "" } },
      ...textTokens("Have confirmed link endpoints (CORE-SYD-01 ↔ CORE-MEL-01). Next: find amplifier sites that amplify this link.", 25, 4),
      // query_graph: amplifier sites
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_fc_q2", name: "query_graph" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_q2", arguments: { query: "MATCH (a:AmplifierSite)-[am:amplifies]->(tl:TransportLink) WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN a.SiteId, a.Location" } } },
      { delayMs: 800, eventType: "tool_result", data: { id: "tc_fc_q2", name: "query_graph", result: FC_QUERY_GRAPH_AMPS } },
      // query_graph: conduit
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_fc_q3", name: "query_graph" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_q3", arguments: { query: "MATCH (tl:TransportLink)-[rt:routed_through]->(pc:PhysicalConduit) WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN pc.ConduitId, pc.RouteDescription" } } },
      { delayMs: 600, eventType: "tool_result", data: { id: "tc_fc_q3", name: "query_graph", result: FC_QUERY_GRAPH_CONDUIT } },
      // query_graph: sensors
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_fc_q4", name: "query_graph" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_q4", arguments: { query: "MATCH (s:Sensor)-[m:monitors_transportlink]->(tl:TransportLink) WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01' RETURN s.SensorId, s.SensorType, s.MountLocation" } } },
      { delayMs: 800, eventType: "tool_result", data: { id: "tc_fc_q4", name: "query_graph", result: FC_QUERY_GRAPH_SENSORS } },
      // Thinking
      { delayMs: 200, eventType: "thinking", data: { token: "" } },
      ...textTokens("Identified splice points and sensors along corridor. Next: find depots servicing these sites and pull on-duty rosters.", 25, 4),
      // query_graph: depot Goulburn
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_fc_q5", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_q5", arguments: { query: "MATCH (d:Depot)-[:services_amplifiersite]->(a:AmplifierSite) WHERE a.SiteId = 'AMP-SYD-MEL-GOULBURN' RETURN d.DepotId, d.DepotName" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_q5", name: "query_graph", result: FC_QUERY_GRAPH_DEPOT_GOULBURN } },
      // query_graph: depot Albury
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_q6", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_q6", arguments: { query: "MATCH (d:Depot)-[:services_amplifiersite]->(a:AmplifierSite) WHERE a.SiteId = 'AMP-SYD-MEL-ALBURY' RETURN d.DepotId, d.DepotName" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_q6", name: "query_graph", result: FC_QUERY_GRAPH_DEPOT_ALBURY } },
      // query_graph: depot SYD
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_q7", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_q7", arguments: { query: "MATCH (d:Depot)-[:services_corerouter]->(cr:CoreRouter) WHERE cr.RouterId = 'CORE-SYD-01' RETURN d.DepotId, d.DepotName" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_q7", name: "query_graph", result: FC_QUERY_GRAPH_DEPOT_SYD } },
      // query_graph: depot MEL
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_q8", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_q8", arguments: { query: "MATCH (d:Depot)-[:services_corerouter]->(cr:CoreRouter) WHERE cr.RouterId = 'CORE-MEL-01' RETURN d.DepotId, d.DepotName" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_q8", name: "query_graph", result: FC_QUERY_GRAPH_DEPOT_MEL } },
      // Thinking
      { delayMs: 200, eventType: "thinking", data: { token: "" } },
      ...textTokens("Depots identified. Now pulling on-duty rosters at each depot and checking equipment availability.", 25, 4),
      // query_graph: rosters (Goulburn, SYD, Albury, MEL)
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_fc_r1", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_r1", arguments: { query: "MATCH (dr:DutyRoster)-[:stationed_at]->(d:Depot) WHERE d.DepotId = 'DEPOT-GOULBURN' RETURN dr.PersonName, dr.Email, dr.Phone, dr.Role" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_r1", name: "query_graph", result: FC_QUERY_GRAPH_ROSTER_GOULBURN } },
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_r2", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_r2", arguments: { query: "MATCH (dr:DutyRoster)-[:stationed_at]->(d:Depot) WHERE d.DepotId = 'DEPOT-SYD-CAMPBELLTOWN' RETURN dr.PersonName, dr.Email, dr.Phone, dr.Role" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_r2", name: "query_graph", result: FC_QUERY_GRAPH_ROSTER_SYD } },
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_r3", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_r3", arguments: { query: "MATCH (dr:DutyRoster)-[:stationed_at]->(d:Depot) WHERE d.DepotId = 'DEPOT-ALBURY' RETURN dr.PersonName, dr.Email, dr.Phone, dr.Role" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_r3", name: "query_graph", result: FC_QUERY_GRAPH_ROSTER_ALBURY } },
      { delayMs: 100, eventType: "tool_call_start", data: { id: "tc_fc_r4", name: "query_graph" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_fc_r4", arguments: { query: "MATCH (dr:DutyRoster)-[:stationed_at]->(d:Depot) WHERE d.DepotId = 'DEPOT-MEL-CLAYTON' RETURN dr.PersonName, dr.Email, dr.Phone, dr.Role" } } },
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_fc_r4", name: "query_graph", result: FC_QUERY_GRAPH_ROSTER_MEL } },
      // Thinking
      { delayMs: 200, eventType: "thinking", data: { token: "" } },
      ...textTokens("On-duty coverage exists at all four relevant depots. Now pulling site specs and equipment manifests.", 25, 4),
      // search_infra_specs
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_fc_si1", name: "search_infra_specs" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_si1", arguments: { query: "AMP-SYD-MEL-GOULBURN site access EDFA module spare procedure" } } },
      { delayMs: 1200, eventType: "tool_result", data: { id: "tc_fc_si1", name: "search_infra_specs", result: FC_SEARCH_INFRA } },
      // search_equipment #1
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_fc_se1", name: "search_equipment" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_se1", arguments: { query: "DEPOT-GOULBURN OTDR Viavi T-BERD 4000 Fujikura 90S cleaning kit EDFA module Lumentum S40i" } } },
      { delayMs: 1000, eventType: "tool_result", data: { id: "tc_fc_se1", name: "search_equipment", result: FC_SEARCH_EQUIP_1 } },
      // search_equipment #2
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_fc_se2", name: "search_equipment" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_se2", arguments: { query: "DEPOT-GOULBURN-manifest" } } },
      { delayMs: 800, eventType: "tool_result", data: { id: "tc_fc_se2", name: "search_equipment", result: FC_SEARCH_EQUIP_2 } },
      // search_equipment #3
      { delayMs: 200, eventType: "tool_call_start", data: { id: "tc_fc_se3", name: "search_equipment" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_fc_se3", arguments: { query: "Lumentum S40i spare EDFA module depot" } } },
      { delayMs: 800, eventType: "tool_result", data: { id: "tc_fc_se3", name: "search_equipment", result: FC_SEARCH_EQUIP_3 } },
      // Response tokens
      ...textTokens(FIELD_COORDINATOR_RESPONSE, 20, 4),
      // Done
      { delayMs: 200, eventType: "done", data: {} },
    ],
  },

  // ─── Step 5: Orchestrator continues — tool calls + final summary ────────
  // The orchestrator already has a delegation_start from step 1; the delegation
  // tool results come back and then it continues with its own tool calls.
  // We model this as the orchestrator getting tool_result for the 3 delegations,
  // then making its own tool calls, then streaming the final summary.
  {
    agentId: "orchestrator",
    switchTab: true,
    events: [
      // Tool results for the 3 delegation calls
      { delayMs: 500, eventType: "tool_result", data: { id: "tc_del_ni", name: "delegate_to_agent", result: JSON.stringify({ agent_id: "networkInvestigator", status: "complete", duration_s: 18.4, summary: "Telemetry review confirmed optical degradation and reroute recommendation" }) } },
      { delayMs: 200, eventType: "tool_result", data: { id: "tc_del_ka", name: "delegate_to_agent", result: JSON.stringify({ agent_id: "knowledgeAnalyst", status: "complete", duration_s: 52.3, summary: "Runbook + precedent review completed" }) } },
      { delayMs: 200, eventType: "tool_result", data: { id: "tc_del_fc", name: "delegate_to_agent", result: JSON.stringify({ agent_id: "fieldCoordinator", status: "complete", duration_s: 182.5, summary: "Dispatch prep package ready" }) } },
      // create_incident_ticket
      { delayMs: 600, eventType: "tool_call_start", data: { id: "tc_orch_cit", name: "create_incident_ticket" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_orch_cit", arguments: { severity: "SEV-2", title: "SYD–MEL corridor degradation — LINK-SYD-MEL-FIBRE-01 optical power drop + high BER causing multi-service impact", description: "Automated anomaly burst detected 09:15 with 15 correlated alerts in 30s on SYD–MEL corridor.", affected_services: "VPN-ACME-CORP,VPN-BIGBANK,MOB-5G-MEL-3011,MOB-5G-SYD-2041,MOB-5G-SYD-2042,BB-BUNDLE-MEL-EAST,BB-BUNDLE-SYD-NORTH", assigned_to: "NOC" } } },
      { delayMs: 1500, eventType: "tool_result", data: { id: "tc_orch_cit", name: "create_incident_ticket", result: CREATE_INCIDENT_RESULT } },
      // dispatch_field_engineer
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_orch_dfe", name: "dispatch_field_engineer" } },
      { delayMs: 300, eventType: "tool_call_end", data: { id: "tc_orch_dfe", arguments: { engineer_name: "Dave Mitchell", engineer_email: "dave.mitchell@austtelco.com.au", engineer_phone: "+61-412-555-401", incident_summary: "SYD–MEL corridor transport degradation: LINK-SYD-MEL-FIBRE-01 optical RX power trending down (< -19 dBm) with rising BER.", destination_description: "Goulburn splice/interchange + AMP-SYD-MEL-GOULBURN inline EDFA cabinet (AMP-SYD-MEL-03). Access via fenced compound off Hume Hwy service road; gate code 4527.", destination_latitude: -34.7546, destination_longitude: 149.7186, urgency: "HIGH" } } },
      { delayMs: 2000, eventType: "tool_result", data: { id: "tc_orch_dfe", name: "dispatch_field_engineer", result: DISPATCH_RESULT } },
      // call_engineer
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_orch_ce", name: "call_engineer" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_orch_ce", arguments: { engineer_name: "Dave Mitchell", phone: "+61-412-555-401" } } },
      { delayMs: 3000, eventType: "tool_result", data: { id: "tc_orch_ce", name: "call_engineer", result: CALL_ENGINEER_RESULT } },
      // update_advisory
      { delayMs: 300, eventType: "tool_call_start", data: { id: "tc_orch_ua", name: "update_advisory" } },
      { delayMs: 200, eventType: "tool_call_end", data: { id: "tc_orch_ua", arguments: { message: "Degrading optical conditions on LINK-SYD-MEL-FIBRE-01 are driving widespread SYD–MEL service quality degradation." } } },
      { delayMs: 1500, eventType: "tool_result", data: { id: "tc_orch_ua", name: "update_advisory", result: UPDATE_ADVISORY_RESULT } },
      // Final summary text
      ...textTokens(ORCHESTRATOR_SUMMARY, 20, 4),
      // Done
      { delayMs: 200, eventType: "done", data: {} },
    ],
  },
];
