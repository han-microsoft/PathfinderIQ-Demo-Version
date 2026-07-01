# Query Language: Gremlin (Cosmos DB graph)

Write **Apache TinkerPop Gremlin** traversals for the `query_graph` tool. The
topology graph is **Cosmos DB Gremlin** — this is **not** GQL, not Cypher, not
SQL.

## Syntax rules

- Every traversal **starts with `g.`** and is read-only. Write steps
  (`addV`, `addE`, `drop`, `property(...)`) are blocked.
- Start from vertices: `g.V()` (all), `g.V('<id>')` (by id),
  `g.V().hasLabel('CoreRouter')`, `g.V().has('City','Sydney')`.
- Entity IDs are the vertex `id`, UPPERCASE with hyphens: `'CORE-SYD-01'`.
- Traverse edges by label and direction:
  - outgoing: `.out('<edge>')` / `.outE('<edge>').inV()`
  - incoming: `.in('<edge>')`
  - both: `.both('<edge>')`
- Return properties with `.valueMap(true)` (includes `id` + `label`) or
  `.values('<prop>')`. **Cosmos Gremlin does not return id/label via
  `.valueMap('id','label')`** — use `.valueMap(true)`, or `.id()` / `.label()`.
- A `.limit(N)` is injected automatically if you omit it. Aggregates
  (`.count()`, `.groupCount()`, `.dedup()`) run uncapped.
- **Anonymous steps inside `project()`/`by()`/`where()` that use a Groovy
  reserved word (`in`, `and`, `or`, `not`, `is`) must be prefixed with `__.`** —
  write `__.in('amplifies')`, not `in('amplifies')`. A top-level `.in('edge')`
  on the main traversal is fine. (The backend auto-corrects bare anonymous
  reserved steps, but emit `__.` to be safe.)
- One traversal per call.

## Edge labels (source → target)

`connects_source`/`connects_target` (TransportLink→CoreRouter), `uplinks_to`
(AggSwitch→CoreRouter), `backhauls_via` (BaseStation→AggSwitch), `monitors`
(Sensor→entity), `peers` (BGPSession→CoreRouter), `governs` (SLAPolicy→Service),
`services` (Depot→entity), `stationed_at` (DutyRoster→Depot), `depends_on`
(Service→entity), `traverses` (MPLSPath→node), `amplifies`
(AmplifierSite→TransportLink), `routed_through` (TransportLink→PhysicalConduit),
`affects` (Advisory→CoreRouter).

There is **no edge-name suffixing** — use the plain label (`monitors`, not
`monitors_transportlink`). Filter by neighbour label instead:
`...in('monitors').hasLabel('Sensor')`.

## Examples

```groovy
g.V().hasLabel('CoreRouter').valueMap(true)
g.V('LINK-SYD-MEL-FIBRE-01').out('connects_source','connects_target').valueMap(true)
g.V('LINK-SYD-MEL-FIBRE-01').in('traverses').in('depends_on').hasLabel('Service').valueMap(true)
g.V('LINK-SYD-MEL-FIBRE-01').out('routed_through').valueMap(true)
g.V().hasLabel('TransportLink').groupCount().by('LinkType')
```
