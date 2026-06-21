# Search Methodology

## search_runbooks
O-RAN/3GPP SOPs, escalation paths, checklists. Query by fault category + interface.
- "fronthaul eCPRI degradation troubleshooting"
- "URLLC slice SLA breach remediation"
- "PRB congestion load balancing"

## search_tickets
Historical precedent, actual resolution timelines, lessons learned. Query by fault signature.
- "fronthaul optical degradation DU"
- "URLLC latency SLA breach slice"

## search_equipment
gNB/RU/DU/CU vendor specs and capacity sheets. Query by vendor/model or component.

## search_infra_specs
O-RAN architecture (CU/DU split, eCPRI fronthaul), 3GPP slice SST definitions, KPM counters.

## Strategy
1. Start broad (fault type + interface). Refine on noisy results.
2. Cross-reference: runbook procedure → ticket instances → actual resolution times.
3. Synthesize — do not return raw results. Extract: procedure steps, timelines, contacts, lessons.

## Output
- **Applicable Procedures** — numbered steps, cite runbook title + section.
- **Historical Precedent** — date, fault, resolution, timeline, lessons.
