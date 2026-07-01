# Tool: query_alerts — AlertStream only (Cosmos DB NoSQL)

For link/sensor metrics use `query_telemetry`. Backend is **Cosmos DB NoSQL** —
emit **Cosmos SQL** (`SELECT ... FROM c ...`), NOT KQL.

## Cosmos SQL rules
- Read-only `SELECT` only. `SELECT TOP N` is injected if you omit a cap.
- The container alias is `c`. Filter on `c.<field>`.
- `c.SourceNodeId` is the partition key. String comparisons are case-sensitive.
- Order recent-first with `ORDER BY c.Timestamp DESC`. Keep results small (`TOP 10`/`TOP 20`).
- **Do not filter on absolute dates** — use `ORDER BY c.Timestamp DESC` + `TOP N`.

## AlertStream fields
| Field | Notes |
|---|---|
| AlertId | `ALT-20260206-003289` |
| Timestamp | ISO 8601 |
| SourceNodeId | Entity ID (partition key) |
| SourceNodeType | `TransportLink`, `Service`, `CoreRouter`, `BaseStation`, `AggSwitch` |
| AlertType | `FIBRE_CUT`, `OPTICAL_DEGRADATION`, `HIGH_BER`, `BGP_PEER_DOWN`, `SERVICE_DEGRADATION`, `HIGH_LATENCY`, `PACKET_LOSS_SPIKE`, `CAPACITY_EXCEEDED`, `DUPLICATE_ALERT` |
| Severity | `CRITICAL`, `MAJOR`, `WARNING`, `MINOR` |
| Description | free text |
| OpticalPowerDbm | Normal: -8 to -12 |
| BitErrorRate | Normal: < 1e-9 |
| CPUUtilPct | High: > 85 |
| PacketLossPct | High: > 2 |

## Examples
```sql
SELECT TOP 10 c.AlertId, c.Timestamp, c.AlertType, c.Severity, c.OpticalPowerDbm, c.BitErrorRate
FROM c WHERE c.SourceNodeId = 'LINK-SYD-MEL-FIBRE-01'
ORDER BY c.Timestamp DESC

SELECT TOP 20 c.Timestamp, c.SourceNodeId, c.AlertType, c.Severity, c.Description
FROM c WHERE c.Severity IN ('CRITICAL', 'MAJOR')
ORDER BY c.Timestamp DESC
```
