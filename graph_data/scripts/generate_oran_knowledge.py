#!/usr/bin/env python3
"""Author the O-RAN 5G RAN knowledge base (AI Search corpus).

Writes compact, domain-faithful O-RAN/3GPP operational documents into the pack's
data/knowledge/{runbooks,tickets,equipment,infra_specs} dirs. Demo-grade,
synthetic, but technically coherent so semantic/vector retrieval is meaningful.
"""
from __future__ import annotations

from pathlib import Path

KNOW = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "oran-5g-ran" / "data" / "knowledge"

DOCS: dict[str, dict[str, str]] = {
    "runbooks": {
        "RB-FRONTHAUL-DEGRADATION.md": """# Runbook: Fronthaul (eCPRI) Degradation

**Applies to:** FRONTHAUL_DEGRADED alarms on `LINK-FH-*` (DU↔Cell eCPRI/CPRI).

## Symptoms
- Rising eCPRI CRC / FEC errors, optical power below threshold on the fronthaul span.
- Downstream cells show PRB_CONGESTION and falling RRCSuccessPct.
- L1 processing load on the parent DU climbs (possible DU_OVERLOAD).

## Diagnostic steps
1. Confirm the degraded span: query the alarm stream for FRONTHAUL_DEGRADED, note SourceNodeId (LINK-FH-*).
2. Trace topology: `link_target` of the link → affected Cell → `serves` DU.
3. Pull per-cell KPM (PRBUtilPct, RRCSuccessPct) for the cells under that DU; confirm the onset timestamp.
4. Check optical budget: target eCPRI RX power within vendor spec; CRC error rate must be < 1e-9.

## Remediation
- If optical power low: inspect/clean SFP and fibre connectors; reseat the eCPRI module.
- If errors persist: fail the cell carrier over to a redundant fronthaul path or shift load to an adjacent cell.
- Open a P2 (P1 if a GOLD/URLLC slice SLA is breached). Dispatch field tech with OTDR + cleaning kit.

## Escalation
- URLLC slice SLA breach → escalate to P1, notify slice tenant per SLA comms cadence.
""",
        "RB-PRB-CONGESTION.md": """# Runbook: PRB Congestion / Cell Overload

**Applies to:** PRB_CONGESTION alarms when a cell's PRBUtilPct exceeds 90% sustained.

## Triage
1. Identify the congested cells (CellKPM PRBUtilPct > 90%) and their DU.
2. Distinguish demand-driven congestion (high ActiveUEs across slices) from
   fault-driven congestion (upstream fronthaul/midhaul degradation reducing usable capacity).
3. Check RRCSuccessPct — a drop below 95% indicates admission control is rejecting setups.

## Mitigation
- Enable/adjust slice-aware PRB scheduling weights to protect GOLD/URLLC slices.
- Trigger load balancing: hand over best-effort eMBB/mMTC UEs to neighbour cells.
- If fault-driven, follow the fronthaul degradation runbook for the parent span.

## Do not
- Do not blanket-throttle URLLC slices to relieve PRB — this trades a capacity issue for an SLA breach.
""",
        "RB-URLLC-SLA-BREACH.md": """# Runbook: URLLC Slice SLA Breach

**Applies to:** SLA_BREACH alarms on URLLC slices (e.g. SL-URLLC-01, 5 ms latency floor).

## Confirm
1. SliceKPM LatencyMs for the slice vs its SLAPolicy MaxLatencyMs.
2. Identify carrying cells: Slice ← carries ← Cell; confirm which are congested.
3. Identify the tenant (Slice.TenantName) and SLAPolicy PenaltyPerHourUSD / Tier.

## Quantify exposure
- Penalty exposure = PenaltyPerHourUSD × breach duration (hours). GOLD URLLC tiers carry the highest rate.

## Remediation priority
1. Restore the URLLC latency budget first: protect PRB for the URLLC slice on affected cells.
2. Address the root-cause span (fronthaul/midhaul) in parallel.
3. Notify the tenant per the SLA communication cadence; log the breach window for penalty reconciliation.
""",
        "RB-RRC-SETUP-FAILURE.md": """# Runbook: RRC Setup Failure Spike

**Applies to:** RRC_SETUP_FAILURE alarms / RRCSuccessPct < 95% on a cell.

## Causes
- PRB exhaustion (admission control rejection) — most common under congestion.
- Fronthaul/transport degradation breaking L1/L2 timing.
- PCI confusion / neighbour mis-config (check PCI vs neighbour list).

## Steps
1. Correlate the RRC failure onset with CellKPM PRBUtilPct and any FRONTHAUL_DEGRADED alarm.
2. If congestion-driven, apply the PRB congestion runbook.
3. If transport-driven, apply the fronthaul degradation runbook.
4. Verify PCI uniqueness within the cell's neighbour set.
""",
        "RB-SLICE-LOAD-BALANCING.md": """# Runbook: Slice-Aware Load Balancing

**Goal:** Protect GOLD/URLLC slice KPIs while relieving cell PRB pressure.

## Levers
- Per-slice PRB reservation: guarantee a minimum PRB share to URLLC, cap mMTC.
- Inter-cell handover of eMBB/mMTC UEs to lightly loaded neighbours.
- Carrier aggregation: add a secondary cell for best-effort traffic.

## Procedure
1. Read SliceKPM PRBUtilPct + ActiveUEs across the affected cells.
2. Raise URLLC slice scheduling weight; lower mMTC weight.
3. Re-measure URLLC LatencyMs after one KPM window; confirm it returns below SLA.
""",
    },
    "tickets": {
        "TKT-2025-03-14-0188.txt": """INCIDENT TKT-2025-03-14-0188
Date: 2025-03-14
Severity: P1
Site: gNB-SYD-02 / DU-SYD-02-1
Fault: FRONTHAUL_DEGRADED on LINK-FH-CELL-SYD-02-1-2; eCPRI CRC errors, RX optical -24 dBm.
Impact: 3 cells PRB > 92%, URLLC slice SL-URLLC-02 latency peaked 11 ms (SLA 8 ms). Tenant RoboticsAU.
Root cause: contaminated LC connector on fronthaul patch after maintenance.
Resolution: cleaned + reseated SFP, RX returned to -9 dBm; PRB and slice latency normalised in 18 min.
Time to resolve: 42 min. Penalty window: 26 min.
Lessons: enforce connector inspection sign-off after any fronthaul maintenance.
""",
        "TKT-2025-04-02-0241.txt": """INCIDENT TKT-2025-04-02-0241
Date: 2025-04-02
Severity: P2
Site: gNB-BNE-01 / DU-BNE-01-2
Fault: PRB_CONGESTION, demand-driven (stadium event). PRBUtil 95% across 2 cells.
Impact: eMBB throughput down 40%; URLLC unaffected (slice PRB reservation held).
Resolution: enabled carrier aggregation + handed over eMBB UEs to neighbour cell; PRB to 71%.
Time to resolve: 35 min.
Lessons: pre-provision event-driven PRB reservation profiles for known venues.
""",
        "TKT-2025-04-21-0307.txt": """INCIDENT TKT-2025-04-21-0307
Date: 2025-04-21
Severity: P1
Site: gNB-MEL-01 / DU-MEL-01-2
Fault: FRONTHAUL_DEGRADED cascading to RRC_SETUP_FAILURE; URLLC SL-URLLC-01 SLA breach (>10 ms vs 5 ms).
Impact: SmartGridCo URLLC traffic degraded; penalty exposure at GOLD rate.
Root cause: dark-fibre fronthaul span attenuation after rodent damage in conduit.
Resolution: failed cells over to redundant fronthaul; dispatched OTDR team; spliced damaged span.
Time to resolve: 1 h 38 min. Penalty window: 1 h 12 min.
Lessons: prioritise URLLC PRB protection immediately on fronthaul fault; redundant FH path cut MTTR.
""",
        "TKT-2025-05-09-0355.txt": """INCIDENT TKT-2025-05-09-0355
Date: 2025-05-09
Severity: P3
Site: gNB-PER-02
Fault: CLOCK_DRIFT (PTP) MINOR; within tolerance, no KPI impact.
Resolution: monitored; GM clock reselection auto-corrected.
Time to resolve: n/a (auto).
Lessons: baseline PTP drift alarms as MINOR; do not page on-call.
""",
        "TKT-2025-05-30-0402.txt": """INCIDENT TKT-2025-05-30-0402
Date: 2025-05-30
Severity: P2
Site: gNB-SYD-01 / DU-SYD-01-1
Fault: RRC_SETUP_FAILURE from PCI collision after neighbour add.
Impact: RRCSuccessPct dropped to 88% on one cell.
Resolution: reassigned PCI to remove mod-3 collision; success rate to 99.4%.
Time to resolve: 27 min.
Lessons: validate PCI plan (mod-3/mod-30) before neighbour list changes.
""",
    },
    "equipment": {
        "EQ-RU-ERICSSON-AIR6488.md": """# Equipment: Ericsson AIR 6488 (Massive MIMO Radio)

- Type: 64T64R mMIMO AAS radio unit, band n78 (3.4–3.8 GHz).
- Fronthaul: eCPRI over 25G; CPRI fallback.
- Max bandwidth: 100 MHz; up to 273 PRB at 30 kHz SCS.
- Power: typical 0.9 kW; integrated antenna.
- Field notes: verify eCPRI RX optical -8 to -12 dBm; CRC errors must be < 1e-9.
""",
        "EQ-DU-NOKIA-AIRSCALE.md": """# Equipment: Nokia AirScale System Module (DU)

- Type: baseband / Distributed Unit, supports split 7.2x fronthaul.
- Capacity: up to 24 cells, 4-layer MIMO per cell at numerology mu=1 (30 kHz).
- Interfaces: F1 (midhaul) to CU; eCPRI to RUs.
- Field notes: L1 load rises sharply when fronthaul degrades — watch for DU_OVERLOAD.
""",
        "EQ-CU-SAMSUNG-VRAN.md": """# Equipment: Samsung vRAN 3.0 CU (CU-CP + CU-UP)

- Type: virtualised Centralised Unit on COTS server, CU-CP and CU-UP co-located.
- Interfaces: N2/N3 to 5GC, F1 to DUs, E1 internal.
- Scaling: per-slice user-plane instances; supports S-NSSAI based routing.
- Field notes: software version drift across CUs can cause F1 setup anomalies.
""",
        "EQ-TRANSPORT-FRONTHAUL.md": """# Equipment: Fronthaul Transport (eCPRI / Dark Fibre)

- Media: dark fibre or WDM, 10–25 Gbps eCPRI per cell carrier.
- Latency budget: one-way fronthaul < 100 µs (split 7.2x).
- Optical budget: maintain RX within radio spec; clean connectors per maintenance.
- Field notes: degradation manifests as CRC/FEC errors then PRB congestion downstream.
""",
    },
    "infra_specs": {
        "SPEC-ORAN-CUDU-SPLIT.md": """# Spec: O-RAN CU/DU Functional Split

The O-RAN architecture decomposes the gNB into CU, DU, and RU.
- **CU** hosts higher-layer functions (RRC, SDAP, PDCP), connects to the 5GC over N2/N3.
- **DU** hosts RLC/MAC/High-PHY; connects to CU over the F1 midhaul interface.
- **RU** hosts Low-PHY/RF; connects to DU over the open fronthaul (split 7.2x, eCPRI).
Open fronthaul enables multi-vendor RU/DU. Fronthaul faults propagate downstream as
cell-level PRB congestion and RRC setup failures.
""",
        "SPEC-3GPP-SLICE-SST.md": """# Spec: 3GPP Network Slice Types (S-NSSAI / SST)

A slice is identified by S-NSSAI (SST + optional SD).
- **eMBB (SST 1):** high throughput, latency-tolerant (10–25 ms). Consumer/video.
- **URLLC (SST 2):** ultra-reliable low-latency (≤ 5 ms typical). Industrial, grid, robotics.
- **mMTC (SST 3):** massive IoT, latency-tolerant (≥ 100 ms), low throughput.
Each slice maps to an SLAPolicy (latency floor, throughput floor, penalty, tier).
URLLC GOLD tiers carry the highest penalty exposure on breach.
""",
        "SPEC-KPM-COUNTERS.md": """# Spec: O-RAN / 3GPP KPM Counter Reference

Key Performance Measurement counters used in this scenario:
- **PRBUtilPct** — physical resource block utilisation; > 90% indicates congestion.
- **RRCSuccessPct** — RRC connection setup success; < 95% indicates admission failures.
- **DLThroughputMbps** — cell downlink throughput.
- **LatencyMs (slice)** — slice user-plane latency; compare to SLA floor.
- **CQI / BLERPct (UE)** — channel quality and block error rate; CQI < 6 or BLER > 10% is poor.
KPMs are reported by the E2 nodes (DU/CU) and collected per cell/slice/UE.
""",
        "SPEC-FRONTHAUL-ECPRI.md": """# Spec: Open Fronthaul (eCPRI, Split 7.2x)

The O-RAN 7.2x fronthaul carries IQ/PRB data between DU and RU over eCPRI.
- Transport: Ethernet/eCPRI over dark fibre or WDM, 10–25 Gbps per carrier.
- Timing: requires tight sync (PTP/SyncE); clock drift degrades performance.
- Health indicators: optical RX power, CRC/FEC error rate, one-way delay.
- Failure mode: rising CRC errors reduce usable capacity → cell PRB congestion →
  RRC setup failures → slice SLA breach if a URLLC slice is carried on the cell.
""",
    },
}


def main() -> None:
    total = 0
    for category, files in DOCS.items():
        d = KNOW / category
        d.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (d / name).write_text(content, encoding="utf-8")
            total += 1
        print(f"  {category}: {len(files)} docs")
    print(f"KB_DONE total={total}")


if __name__ == "__main__":
    main()
