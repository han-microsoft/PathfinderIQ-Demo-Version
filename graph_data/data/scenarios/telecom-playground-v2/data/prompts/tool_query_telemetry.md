# Tool: query_telemetry — LinkTelemetry + SensorReadings

For alerts use `query_alerts`. Never mix columns between tables.

## KQL rules
- Start with table name. No SQL.
- String comparisons case-sensitive. Use `==`.
- **NEVER filter Timestamp** — no `ago()`, `now()`. Use `top N by Timestamp desc`.
- `top 10` or `top 20`. Use `summarize` for aggregates.
- `PacketLossPct` and `CPUUtilPct` do NOT exist in these tables.

## LinkTelemetry — 5-min interval link metrics

| Column | Type | Notes |
|---|---|---|
| LinkId | string | FK → TransportLink |
| Timestamp | datetime | |
| UtilizationPct | real | High: > 80 |
| OpticalPowerDbm | real | Normal: -8 to -12. Dead: -35 |
| BitErrorRate | real | Normal: < 1e-9. Dead: 1.0 |
| LatencyMs | real | Normal: 2-15. Dead: 9999 |

## SensorReadings — per-sensor physical measurements

| Column | Type | Notes |
|---|---|---|
| ReadingId | string | |
| Timestamp | datetime | |
| SensorId | string | FK → Sensor |
| SensorType | string | `OpticalPower`, `BitErrorRate`, `Temperature`, `CPULoad` |
| Value | real | |
| Unit | string | dBm, ratio, °C, % |
| Status | string | `NORMAL`, `WARNING`, `CRITICAL` |

## Examples

```kql
LinkTelemetry
| where LinkId == 'LINK-SYD-MEL-FIBRE-01'
| top 10 by Timestamp desc
| project Timestamp, LinkId, UtilizationPct, OpticalPowerDbm, BitErrorRate, LatencyMs

SensorReadings
| where SensorId startswith 'SENS-SYD-MEL-F1'
| where Status != 'NORMAL'
| top 20 by Timestamp desc
| project Timestamp, SensorId, SensorType, Value, Unit, Status
```
