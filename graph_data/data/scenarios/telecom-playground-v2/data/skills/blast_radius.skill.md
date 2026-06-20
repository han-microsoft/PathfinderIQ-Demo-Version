# Skill: Blast Radius Assessment

Determine which customer services and SLAs a failed network element impacts.

## Steps
1. From the failed element, traverse the dependency graph to services
   (`query_graph`):
   `g.V('<LinkId>').in('traverses').in('depends_on').hasLabel('Service').valueMap(true)`.
2. For each impacted service, find its SLA
   (`g.V().hasLabel('SLAPolicy').has('ServiceId','<id>').valueMap(true)`) and
   note `Tier` + `PenaltyPerHourUSD`.
3. Check shared-risk: `g.V('<LinkId>').out('routed_through')` — links in the
   same conduit are NOT physically diverse.
4. Rank impact by customer count and SLA penalty.

## Tags
blast-radius, impact, services, sla, dependency, shared-risk
