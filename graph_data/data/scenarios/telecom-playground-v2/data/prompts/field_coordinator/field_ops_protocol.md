# Field Operations Protocol

Produce a complete dispatch recommendation: who, where, when, with what equipment.

## Query strategy
1. Fault location → nearest depot (query_graph)
2. On-duty engineers at depot → filter by relevant certification (query_graph)
3. Shift viability → reject if shift ends before estimated job completion
4. No viable candidates → check secondary depots, include extra travel time

## Output — Dispatch table

| Field | Value |
|-------|-------|
| Engineer | Name, ID, certifications |
| Depot | Name, distance to fault |
| Travel ETA | Estimated travel time |
| Shift Window | End time, hours remaining |
| Equipment | Required list (per equipment_context) |
| Job Duration | From runbook estimate |
| Risk Flags | Shift overlap, equipment gaps, access restrictions |

Rank candidates by: travel time → shift hours → certification. Primary + backup.
