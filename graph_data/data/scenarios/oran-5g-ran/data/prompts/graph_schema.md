# Graph Schema Reference — O-RAN 5G RAN Topology Ontology

Entity types, property schemas, and relationships. **Do not memorise instance
data from this file** — query the graph for actual values.

---

## Entity Types

### CoreNetwork
National 5G core (5GC). Single node. Properties: CoreId, Name, Region, NSSF, AMF.

### gNB
5G NR base station (gNodeB). `GNB-{CITY}-{NN}`. Properties: gNBId, Name, City,
Region, Vendor, Model, Latitude, Longitude.

### CU
Centralised Unit (CU-CP+UP). `CU-{CITY}-{NN}`. Properties: CUId, gNBId, CUType,
SoftwareVersion. One CU per gNB.

### DU
Distributed Unit. `DU-{CITY}-{NN}-{D}`. Properties: DUId, gNBId, CUId, Numerology,
MaxLayers. Two DUs per gNB.

### Cell
NR cell / sector. `CELL-{CITY}-{NN}-{D}-{C}`. Properties: CellId, DUId, Band
(n78/n28/n258), FreqMHz, PCI, AzimuthDeg, MaxPRB. Three cells per DU.

### Slice
Network slice (3GPP S-NSSAI). `SL-{SST}-{NN}`. Properties: SliceId, SST
(eMBB/URLLC/mMTC), SNSSAI, SLALatencyMs, SLAThroughputMbps, TenantName.

### SLAPolicy
SLA commitment per slice. `SLAP-{SliceId}`. Properties: SLAPolicyId, SliceId,
MaxLatencyMs, MinThroughputMbps, PenaltyPerHourUSD, Tier (GOLD/SILVER/STANDARD).

### UE
User-equipment cohort. `UE-{CellId}-{K}`. Properties: UEId, CellId, SliceId,
DeviceClass, SubscriberCount.

### TransportLink
Fronthaul (eCPRI, DU↔Cell), midhaul (F1, CU↔DU), or backhaul (N3, gNB↔Core).
`LINK-FH-*` / `LINK-MH-*` / `LINK-BH-*`. Properties: LinkId, LinkType, SourceId,
TargetId, CapacityGbps, MediaType.

---

## Relationships (Gremlin edge labels)

Backend is Cosmos DB Gremlin. Edges are directed **source → target**; traverse
with `.out()` (outgoing), `.in()` (incoming), `.both()`.

| Edge | Source → Target | Notes |
|---|---|---|
| `hosts` | gNB → CU, gNB → DU | gNB owns its CU and DUs |
| `controls` | CU → DU | F1 control |
| `serves` | DU → Cell | DU drives cells |
| `carries` | Cell → Slice | cell carries slice traffic (many-to-many) |
| `attached_to` | UE → Cell | UE camped on cell |
| `uses` | UE → Slice | UE on slice |
| `governed_by` | Slice → SLAPolicy | slice SLA |
| `link_source` | TransportLink → element | link's source endpoint |
| `link_target` | TransportLink → element | link's target endpoint |

### Key traversals

- **Slice blast radius (cells/DUs):** `g.V('<SliceId>').in('carries').hasLabel('Cell').in('serves').hasLabel('DU').valueMap(true)`
- **Slice tenants/UEs:** `g.V('<SliceId>').in('uses').hasLabel('UE').valueMap(true)`
- **Fronthaul link feeding a cell:** `g.V('<CellId>').in('link_target').hasLabel('TransportLink').valueMap(true)`
- **SLA policy for a slice:** `g.V('<SliceId>').out('governed_by').valueMap(true)`
- **Cells under a DU:** `g.V('<DUId>').out('serves').valueMap(true)`
