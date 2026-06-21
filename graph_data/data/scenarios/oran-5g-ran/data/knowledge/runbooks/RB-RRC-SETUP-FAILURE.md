# Runbook: RRC Setup Failure Spike

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
