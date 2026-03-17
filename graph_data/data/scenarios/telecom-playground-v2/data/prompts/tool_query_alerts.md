# Tool: query_alerts — AlertStream only

For link metrics use `query_telemetry`. Never mix columns between tables.

## KQL rules
- Start with table name. No SQL (`SELECT`, `GROUP BY`, `LIMIT`).
- String comparisons case-sensitive. Use `==`.
- **NEVER filter Timestamp** — no `ago()`, `now()`, absolute dates. Use `top N by Timestamp desc`.
- Keep results small: `top 10` or `top 20`.

## AlertStream columns

| Column | Type | Notes |
|---|---|---|
| AlertId | string | `ALT-20260206-003289` |
| Timestamp | datetime | |
| SourceNodeId | string | Entity ID |
| SourceNodeType | string | `TransportLink`, `Service`, `CoreRouter`, `BaseStation`, `AggSwitch` |
| AlertType | string | `FIBRE_CUT`, `OPTICAL_DEGRADATION`, `HIGH_BER`, `BGP_PEER_DOWN`, `SERVICE_DEGRADATION`, `HIGH_LATENCY`, `PACKET_LOSS_SPIKE`, `CAPACITY_EXCEEDED`, `DUPLICATE_ALERT` |
| Severity | string | `CRITICAL`, `MAJOR`, `WARNING`, `MINOR` |
| Description | string | |
| OpticalPowerDbm | real | Normal: -8 to -12 |
| BitErrorRate | real | Normal: < 1e-9 |
| CPUUtilPct | real | High: > 85 |
| PacketLossPct | real | High: > 2 |

`CPUUtilPct` and `PacketLossPct` exist ONLY in AlertStream.

## Examples

```kql
AlertStream
| where SourceNodeId == 'LINK-SYD-MEL-FIBRE-01'
| top 10 by Timestamp desc
| project AlertId, Timestamp, AlertType, Severity, OpticalPowerDbm, BitErrorRate

AlertStream
| where Severity in ('CRITICAL', 'MAJOR')
| top 20 by Timestamp desc
| project Timestamp, SourceNodeId, AlertType, Severity, Description
```
