# Runbook: Fronthaul (eCPRI) Degradation

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
