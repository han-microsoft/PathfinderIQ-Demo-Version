# Query Language: GQL (Microsoft Fabric)

Write **GQL** (ISO/IEC 39075) queries for the `query_graph` tool. GQL is
declarative MATCH/RETURN — **not** GraphQL, not Gremlin.

## Syntax rules

- `MATCH (alias:Label)-[alias:edge]->(alias:Label)` pattern matching.
- Filter with `WHERE`. String literals use **single quotes**: `'CORE-SYD-01'`.
- **Entity IDs are UPPERCASE** — never use `LOWER()`.
- **One MATCH/RETURN per call.** Multiple statements return empty results.
- **No OPTIONAL MATCH** — use separate queries instead.
- **No DISTINCT** — deduplicate in your analysis.
- **Aliases required** on all nodes and relationships.

## CRITICAL — disambiguated edge names

Two edges are **suffixed by target type** in Fabric GQL. Using the bare name
returns **zero results**:

| Bare (WRONG) | Suffixed (CORRECT) |
|---|---|
| `monitors` | `monitors_transportlink`, `monitors_corerouter`, `monitors_amplifiersite` |
| `services` | `services_corerouter`, `services_amplifiersite` |

All other edges use plain names: `connects_to`, `routes_via`, `depends_on_mplspath`,
`aggregates_to`, `backhauls_via`, `governed_by`, `peers_over`, `amplifies`,
`routed_through`, `stationed_at`, `affects_version`.

## Examples

**These show GQL syntax patterns only.** Substitute the actual entity
IDs from your investigation — do not copy-paste the IDs shown here.

### 1-hop queries

```gql
-- Sensors on a link (MUST use monitors_transportlink)
MATCH (s:Sensor)-[m:monitors_transportlink]->(tl:TransportLink)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN s.SensorId, s.SensorType, s.MountLocation, s.Latitude, s.Longitude

-- Depot that services a router (MUST use services_corerouter)
MATCH (d:Depot)-[sv:services_corerouter]->(cr:CoreRouter)
WHERE cr.RouterId = 'CORE-SYD-01'
RETURN d.DepotId, d.DepotName, d.City, d.Latitude, d.Longitude

-- Depot that services an amplifier (MUST use services_amplifiersite)
MATCH (d:Depot)-[sv:services_amplifiersite]->(a:AmplifierSite)
WHERE a.SiteId = 'AMP-SYD-MEL-GOULBURN'
RETURN d.DepotId, d.DepotName, d.City

-- Engineers at a depot
MATCH (dr:DutyRoster)-[st:stationed_at]->(d:Depot)
WHERE d.DepotId = 'DEPOT-GOULBURN'
RETURN dr.PersonName, dr.Email, dr.Phone, dr.Role, dr.ShiftStart, dr.ShiftEnd

-- MPLS paths traversing a link
MATCH (mp:MPLSPath)-[r:routes_via]->(tl:TransportLink)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN mp.PathId, mp.PathType

-- Routers a link connects to
MATCH (tl:TransportLink)-[c:connects_to]->(cr:CoreRouter)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN cr.RouterId, cr.City
```

### Multi-hop queries

```gql
-- Link → paths → services (2-hop blast radius)
MATCH (tl:TransportLink)<-[r:routes_via]-(mp:MPLSPath)<-[d:depends_on_mplspath]-(svc:Service)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN mp.PathId, mp.PathType, svc.ServiceId, svc.CustomerName, svc.ServiceType

-- SLA policies for specific services (run as second query)
MATCH (sla:SLAPolicy)-[g:governed_by]->(svc:Service)
WHERE svc.ServiceId IN ['VPN-ACME-CORP', 'VPN-BIGBANK']
RETURN svc.ServiceId, sla.SLAPolicyId, sla.Tier, sla.PenaltyPerHourUSD

-- Fault → depot → engineer (via amplifier site)
MATCH (dr:DutyRoster)-[st:stationed_at]->(d:Depot)-[sv:services_amplifiersite]->(a:AmplifierSite)
WHERE a.SiteId = 'AMP-SYD-MEL-GOULBURN'
RETURN dr.PersonName, dr.Email, dr.Phone, d.DepotName
```

### Depot ↔ TransportLink (no direct edge — two queries needed)

```gql
-- Query 1: via CoreRouter
MATCH (tl:TransportLink)-[c:connects_to]->(cr:CoreRouter)<-[sv:services_corerouter]-(d:Depot)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN d.DepotId, d.DepotName, cr.RouterId

-- Query 2: via AmplifierSite (separate call)
MATCH (d:Depot)-[sv:services_amplifiersite]->(a:AmplifierSite)-[am:amplifies]->(tl:TransportLink)
WHERE tl.LinkId = 'LINK-SYD-MEL-FIBRE-01'
RETURN d.DepotId, d.DepotName, a.SiteId
```