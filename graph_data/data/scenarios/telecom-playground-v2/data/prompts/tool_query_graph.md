# Tool: query_graph — Gremlin topology traversal (Cosmos DB graph)

Query network topology: infrastructure, sensors, GPS, depots, duty rosters.
Backend is **Cosmos DB Gremlin (Apache TinkerPop)** — emit Gremlin traversals,
NOT GQL/Cypher/SQL.

## Rules
- Every traversal **must start with `g.`** and be read-only (no `addV`/`addE`/`drop`/`property(...)` write steps).
- Entity IDs are the vertex `id` (UPPERCASE with hyphens): `CORE-SYD-01`, `LINK-SYD-MEL-FIBRE-01`.
- `.limit(N)` is injected automatically if you omit it. Aggregates (`.count()`, `.groupCount()`) are left uncapped.
- One traversal per call. Multiple queries = multiple calls.
- Query error → read message, fix syntax, retry once.
- Use `.valueMap(true)` to include `id` + `label` with properties.

## Vertex labels
`CoreRouter`, `AggSwitch`, `BaseStation`, `TransportLink`, `Service`, `Sensor`,
`MPLSPath`, `PhysicalConduit`, `AmplifierSite`, `BGPSession`, `SLAPolicy`,
`Advisory`, `Depot`, `DutyRoster`.

## Edge labels (out-direction: source → target)
| Edge | Source → Target |
|---|---|
| `connects_source` / `connects_target` | TransportLink → CoreRouter |
| `uplinks_to` | AggSwitch → CoreRouter |
| `backhauls_via` | BaseStation → AggSwitch |
| `monitors` | Sensor → TransportLink/CoreRouter/AmplifierSite |
| `peers` | BGPSession → CoreRouter |
| `governs` | SLAPolicy → Service |
| `services` | Depot → CoreRouter/AmplifierSite |
| `stationed_at` | DutyRoster → Depot |
| `depends_on` | Service → MPLSPath/AggSwitch/BaseStation |
| `traverses` | MPLSPath → CoreRouter/TransportLink |
| `amplifies` | AmplifierSite → TransportLink |
| `routed_through` | TransportLink → PhysicalConduit |
| `affects` | Advisory → CoreRouter |

Traverse incoming edges with `.in('<edge>')` / `.inE()`, outgoing with
`.out('<edge>')` / `.outE()`, either with `.both('<edge>')`.

## Examples
```groovy
// All core routers with their properties
g.V().hasLabel('CoreRouter').valueMap(true)

// What a link connects to (use valueMap(true) to see id + label — Cosmos
// Gremlin does NOT return id/label via valueMap('id','label'))
g.V('LINK-SYD-MEL-FIBRE-01').out('connects_source','connects_target').valueMap(true)

// Services impacted by a link (link ← traverses ← MPLSPath ← depends_on ← Service)
g.V('LINK-SYD-MEL-FIBRE-01').in('traverses').in('depends_on').hasLabel('Service').valueMap(true)

// Which conduit a link is routed through (shared-risk detection)
g.V('LINK-SYD-MEL-FIBRE-01').out('routed_through').valueMap(true)

// Fault → dispatch: there is NO direct depot→link edge. Hop via the link's
// core routers: link → CoreRouter ← services ← Depot ← stationed_at ← DutyRoster
g.V('LINK-SYD-MEL-FIBRE-01').out('connects_source','connects_target').in('services').in('stationed_at').hasLabel('DutyRoster').valueMap(true)
```
