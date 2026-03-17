# Equipment Context

## Fault → Equipment mapping

| Fault Type | Required Equipment |
|---|---|
| Fibre break | OTDR (Viavi T-BERD 4000), Fusion Splicer (Fujikura 90S), Power Meter |
| Fibre degradation | OTDR, Power Meter |
| Connector fault | OTDR, Power Meter, cleaning kit |
| Node power failure | UPS / Portable Power, multimeter |
| RF link degradation | RF Test Kit |

## Availability check
Use `search_equipment` by type + depot. If unavailable at nearest depot → check adjacent depots → flag as blocker if no equipment within radius.
