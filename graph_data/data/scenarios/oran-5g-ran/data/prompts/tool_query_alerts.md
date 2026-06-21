# Tool: query_alerts — AlarmStream only (Cosmos DB NoSQL)

For KPM metrics use `query_telemetry`. Backend is **Cosmos DB NoSQL** — emit
**Cosmos SQL** (`SELECT ... FROM c ...`), NOT KQL.

## Cosmos SQL rules
- Read-only `SELECT` only. `SELECT TOP N` is injected if you omit a cap.
- The container alias is `c`. Filter on `c.<field>`.
- `c.SourceNodeId` is the partition key (the affected element id). Case-sensitive.
- Order recent-first with `ORDER BY c.Timestamp DESC`. Keep results small (`TOP 10`/`TOP 20`).
- **Do not filter on absolute dates** — use `ORDER BY c.Timestamp DESC` + `TOP N`.

## AlarmStream fields
| Field | Notes |
|---|---|
| AlarmId | `ALM-00001` |
| Timestamp | ISO 8601 |
| SourceNodeId | Affected element id (partition key): gNB / DU / Cell / Slice / LINK-* |
| AlarmType | `FRONTHAUL_DEGRADED`, `PRB_CONGESTION`, `RRC_SETUP_FAILURE`, `SLA_BREACH`, `DU_OVERLOAD`, `CLOCK_DRIFT` |
| Severity | `CRITICAL`, `MAJOR`, `MINOR` |
| Description | free text |
| SliceId | set on slice-scoped alarms (e.g. SLA_BREACH) |

## Examples
```sql
SELECT TOP 20 c.Timestamp, c.SourceNodeId, c.AlarmType, c.Severity, c.Description
FROM c WHERE c.Severity IN ('CRITICAL', 'MAJOR')
ORDER BY c.Timestamp DESC

SELECT TOP 10 c.AlarmId, c.Timestamp, c.AlarmType, c.Severity, c.Description
FROM c WHERE c.SourceNodeId = 'SL-URLLC-01'
ORDER BY c.Timestamp DESC
```
