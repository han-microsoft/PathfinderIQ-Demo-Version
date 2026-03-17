# Search Methodology

## search_runbooks
SOPs, escalation paths, checklists. Query by fault category + equipment type.
- "fibre break splice procedure trunk span"
- "OLT power failure escalation"

## search_tickets
Historical precedent, actual resolution timelines, lessons learned. Query by fault signature/location.
- "fibre break span SE-7"
- "CKT-4821 outage resolution"

## Strategy
1. Start broad (fault type + equipment). Refine on noisy results.
2. Cross-reference: runbook procedure → ticket instances of that procedure → actual resolution times.
3. Synthesize — do not return raw results. Extract: procedure steps, timelines, contacts, lessons.

## Output
- **Applicable Procedures** — numbered steps, cite runbook title + section.
- **Historical Precedent** — date, fault, resolution, timeline, lessons.
