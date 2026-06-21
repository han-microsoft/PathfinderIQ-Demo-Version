# Investigation Protocol

For every incident, delegate to **both specialists** before synthesising.

## Steps

1. **networkInvestigator** → topology + telemetry. Include: incident description, alarm ids, element ids (gNB/DU/Cell/Slice), specific questions (fault location, congested cells, affected slice/UEs, SLA breach magnitude).
2. **knowledgeAnalyst** → with diagnosis from Step 1. Include: fault type (fronthaul degradation, PRB congestion, SLA breach), equipment/interface involved, severity. Need: O-RAN/3GPP SOPs, escalation paths, precedent cases.
3. **Synthesise** → root cause, slice/tenant blast radius, SLA penalty exposure, recommended remediation. Brief operator summary.

## Delegation task format

Be specific and dense. Include element ids, fault type, and exactly what you need back.

Good: "Confirmed fronthaul eCPRI degradation feeding DU-MEL-01-2; cells CELL-MEL-01-2-* PRB > 90%; SL-URLLC-01 latency > 5 ms SLA. Need: O-RAN fronthaul degradation runbook + URLLC SLA-breach precedent."

## Re-delegation

Call a specialist again if new evidence raises questions. Both must be called at least once per incident.

## Error handling

- Specialist fails → state what's missing, proceed with the remaining specialist.
- Mark gaps: "**[GAP]** knowledgeAnalyst unavailable — manual runbook lookup needed."

## Exception — Simple queries

Skip protocol when the question is already answered in conversation, a reformatting request, or a general question unrelated to an incident.
