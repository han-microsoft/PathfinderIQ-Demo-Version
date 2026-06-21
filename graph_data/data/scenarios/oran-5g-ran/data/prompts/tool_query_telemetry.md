# Tool: query_telemetry — slice/cell/UE KPM readings (Cosmos DB NoSQL)

For alarms use `query_alerts`. Backend is **Cosmos DB NoSQL** — emit **Cosmos
SQL** (`SELECT ... FROM c ...`), NOT KQL.

## Cosmos SQL rules
- Read-only `SELECT` only. `SELECT TOP N` is injected if you omit a cap.
- The container alias is `c`. Filter on `c.<field>`.
- One container holds slice, cell, AND UE KPM docs, discriminated by `c.kind`:
  - `c.kind = 'slice'` → per-slice KPMs
  - `c.kind = 'cell'`  → per-cell KPMs
  - `c.kind = 'ue'`    → per-UE KPMs
- Always filter `c.kind`. `c.entityId` is the partition key (SliceId / CellId / UEId).
- Case-sensitive. Order recent-first with `ORDER BY c.Timestamp DESC`.
- **Do not filter on absolute dates** — use `ORDER BY c.Timestamp DESC` + `TOP N`.

## Slice docs (`c.kind = 'slice'`)
| Field | Notes |
|---|---|
| entityId | = SliceId |
| LatencyMs | URLLC SLA floor 5 ms; breach > 5 ms |
| ThroughputMbps | vs slice SLA floor |
| PRBUtilPct | High: > 85 |
| ActiveUEs | count |

## Cell docs (`c.kind = 'cell'`)
| Field | Notes |
|---|---|
| entityId | = CellId |
| PRBUtilPct | Congested: > 90 |
| RRCSuccessPct | Degraded: < 95 |
| DLThroughputMbps | number |

## UE docs (`c.kind = 'ue'`)
| Field | Notes |
|---|---|
| entityId | = UEId |
| CQI | Poor: < 6 |
| ThroughputMbps | number |
| BLERPct | High: > 10 |

## Examples
```sql
SELECT TOP 12 c.Timestamp, c.entityId, c.LatencyMs, c.ThroughputMbps, c.PRBUtilPct
FROM c WHERE c.kind = 'slice' AND c.entityId = 'SL-URLLC-01'
ORDER BY c.Timestamp DESC

SELECT TOP 12 c.Timestamp, c.entityId, c.PRBUtilPct, c.RRCSuccessPct
FROM c WHERE c.kind = 'cell' AND c.entityId = 'CELL-MEL-01-2-1'
ORDER BY c.Timestamp DESC
```
