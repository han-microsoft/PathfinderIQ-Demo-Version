# Runbook: Slice-Aware Load Balancing

**Goal:** Protect GOLD/URLLC slice KPIs while relieving cell PRB pressure.

## Levers
- Per-slice PRB reservation: guarantee a minimum PRB share to URLLC, cap mMTC.
- Inter-cell handover of eMBB/mMTC UEs to lightly loaded neighbours.
- Carrier aggregation: add a secondary cell for best-effort traffic.

## Procedure
1. Read SliceKPM PRBUtilPct + ActiveUEs across the affected cells.
2. Raise URLLC slice scheduling weight; lower mMTC weight.
3. Re-measure URLLC LatencyMs after one KPM window; confirm it returns below SLA.
