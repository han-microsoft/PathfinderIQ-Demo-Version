# Runbook: PRB Congestion / Cell Overload

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
