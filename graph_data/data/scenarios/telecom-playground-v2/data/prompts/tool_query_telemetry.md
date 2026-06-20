# Tool: query_telemetry — link + sensor readings (Cosmos DB NoSQL)

For alerts use `query_alerts`. Backend is **Cosmos DB NoSQL** — emit **Cosmos
SQL** (`SELECT ... FROM c ...`), NOT KQL.

## Cosmos SQL rules
- Read-only `SELECT` only. `SELECT TOP N` is injected if you omit a cap.
- The container alias is `c`. Filter on `c.<field>`.
- One container holds BOTH link and sensor docs, discriminated by `c.kind`:
  - `c.kind = 'link'`   → link metrics
  - `c.kind = 'sensor'` → sensor readings
- Always filter `c.kind`. `c.entityId` is the partition key (LinkId or SensorId).
- String comparisons are case-sensitive. Order recent-first with `ORDER BY c.Timestamp DESC`.
- **Do not filter on absolute dates** — use `ORDER BY c.Timestamp DESC` + `TOP N`.

## Link docs (`c.kind = 'link'`)
| Field | Notes |
|---|---|
| entityId | = LinkId, FK → TransportLink |
| Timestamp | ISO 8601 |
| UtilizationPct | High: > 80 |
| OpticalPowerDbm | Normal: -8 to -12. Dead: -35 |
| BitErrorRate | Normal: < 1e-9. Dead: 1.0 |
| LatencyMs | Normal: 2-15. Dead: 9999 |

## Sensor docs (`c.kind = 'sensor'`)
| Field | Notes |
|---|---|
| entityId | = SensorId, FK → Sensor |
| Timestamp | ISO 8601 |
| SensorType | `OpticalPower`, `BitErrorRate`, `Temperature`, `CPULoad` |
| Value | number |
| Unit | dBm, ratio, °C, % |
| Status | `NORMAL`, `WARNING`, `CRITICAL` |

## Examples
```sql
SELECT TOP 10 c.Timestamp, c.entityId, c.UtilizationPct, c.OpticalPowerDbm, c.BitErrorRate, c.LatencyMs
FROM c WHERE c.kind = 'link' AND c.entityId = 'LINK-SYD-MEL-FIBRE-01'
ORDER BY c.Timestamp DESC

SELECT TOP 20 c.Timestamp, c.entityId, c.SensorType, c.Value, c.Unit, c.Status
FROM c WHERE c.kind = 'sensor' AND STARTSWITH(c.entityId, 'SENS-SYD-MEL-F1') AND c.Status != 'NORMAL'
ORDER BY c.Timestamp DESC
```
