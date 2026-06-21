# Tool: query_graph — Gremlin topology traversal (Cosmos DB graph)

Query the 5G RAN topology: gNB/CU/DU/Cell hierarchy, slices, UEs, SLA policies,
transport links. Backend is **Cosmos DB Gremlin (Apache TinkerPop)** — emit
Gremlin traversals, NOT GQL/Cypher/SQL.

## Rules
- Every traversal **must start with `g.`** and be read-only (no `addV`/`addE`/`drop`/`property(...)` writes).
- Entity IDs are the vertex `id`: `GNB-MEL-01`, `DU-MEL-01-2`, `CELL-MEL-01-2-1`, `SL-URLLC-01`, `LINK-FH-CELL-MEL-01-2-1`.
- `.limit(N)` is injected automatically if you omit it. Aggregates (`.count()`, `.groupCount()`) are left uncapped.
- One traversal per call. Use `.valueMap(true)` to include `id` + `label` with properties.
- Query error → read message, fix syntax, retry once.

## Vertex labels
`CoreNetwork`, `gNB`, `CU`, `DU`, `Cell`, `Slice`, `SLAPolicy`, `UE`, `TransportLink`.

## Edge labels (out-direction: source → target)
| Edge | Source → Target |
|---|---|
| `hosts` | gNB → CU, gNB → DU |
| `controls` | CU → DU |
| `serves` | DU → Cell |
| `carries` | Cell → Slice |
| `attached_to` | UE → Cell |
| `uses` | UE → Slice |
| `governed_by` | Slice → SLAPolicy |
| `link_source` / `link_target` | TransportLink → endpoint element |

Traverse incoming with `.in('<edge>')`, outgoing with `.out('<edge>')`, either with `.both('<edge>')`.

## Examples
```groovy
// All cells served by a DU
g.V('DU-MEL-01-2').out('serves').valueMap(true)

// Which slices a cell carries
g.V('CELL-MEL-01-2-1').out('carries').valueMap(true)

// Which DU/cells carry a slice (blast radius): Slice ← carries ← Cell ← serves ← DU
g.V('SL-URLLC-01').in('carries').hasLabel('Cell').in('serves').hasLabel('DU').valueMap(true)

// UEs and tenants on a slice
g.V('SL-URLLC-01').in('uses').hasLabel('UE').valueMap(true)

// SLA policy governing a slice
g.V('SL-URLLC-01').out('governed_by').valueMap(true)

// Fronthaul link feeding a cell (TransportLink → target element via link_target)
g.V('CELL-MEL-01-2-1').in('link_target').hasLabel('TransportLink').valueMap(true)
```
