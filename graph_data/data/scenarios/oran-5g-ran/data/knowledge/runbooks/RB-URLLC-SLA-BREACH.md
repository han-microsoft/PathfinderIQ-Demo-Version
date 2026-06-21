# Runbook: URLLC Slice SLA Breach

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
