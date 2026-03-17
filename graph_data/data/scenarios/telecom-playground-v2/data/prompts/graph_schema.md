# Graph Schema Reference — Network Topology Ontology

Entity types, property schemas, and relationships. **Do not memorise instance
data from this file** — query the graph for actual values.

---

## Entity Types

### CoreRouter
Backbone routers at city level (Sydney, Melbourne, Brisbane).

| Property | Type | Notes |
|---|---|---|
| **RouterId** | String | PK. Format: `CORE-{CITY}-01` |
| City | String | |
| Region | String | State |
| Vendor | String | Cisco or Juniper |
| Model | String | Hardware model |
| FirmwareVersion | String | Used for Advisory correlation |
| Latitude, Longitude | Double | GPS (WGS84) |

### TransportLink
Physical fibre links. Inter-city backbone (DWDM_100G) or local aggregation uplinks (100GE).

| Property | Type | Notes |
|---|---|---|
| **LinkId** | String | PK. Format: `LINK-{SRC}-{DST}-FIBRE-{N}` or `LINK-{CITY}-AGG-{ZONE}-01` |
| LinkType | String | `DWDM_100G` or `100GE` |
| CapacityGbps | Integer | |
| SourceRouterId | String | FK → CoreRouter |
| TargetRouterId | String | FK → CoreRouter |

### AggSwitch
Aggregation switches between core routers and base stations. Two per city.

| Property | Type | Notes |
|---|---|---|
| **SwitchId** | String | PK. Format: `AGG-{CITY}-{ZONE}-01` |
| City | String | |
| UplinkRouterId | String | FK → CoreRouter |
| Latitude, Longitude | Double | GPS |

### BaseStation
5G NR gNodeBs at the network edge.

| Property | Type | Notes |
|---|---|---|
| **StationId** | String | PK. Format: `GNB-{CITY}-{NUM}` |
| StationType | String | Always `5G_NR` |
| AggSwitchId | String | FK → AggSwitch |
| City | String | |

### BGPSession
Inter-city BGP peering sessions. One per router pair.

| Property | Type | Notes |
|---|---|---|
| **SessionId** | String | PK. Format: `BGP-{CITY1}-{CITY2}-01` |
| PeerARouterId | String | FK → CoreRouter |
| PeerBRouterId | String | FK → CoreRouter |
| ASNumberA, ASNumberB | Integer | |

### MPLSPath
MPLS label-switched paths carrying service traffic between cities.

| Property | Type | Notes |
|---|---|---|
| **PathId** | String | PK. Format: `MPLS-PATH-{SRC}-{DST}-{TIER}` |
| PathType | String | `PRIMARY`, `SECONDARY`, or `TERTIARY` |

### Service
Customer-facing services. Three subtypes.

| Property | Type | Notes |
|---|---|---|
| **ServiceId** | String | PK. Format: `VPN-{NAME}`, `BB-BUNDLE-{CITY}-{ZONE}`, `MOB-5G-{CITY}-{NUM}` |
| ServiceType | String | `EnterpriseVPN`, `Broadband`, or `Mobile5G` |
| CustomerName | String | |
| CustomerCount | Integer | 1 for VPN, thousands for broadband/mobile |
| ActiveUsers | Integer | |

### SLAPolicy
SLA commitments governing services. Not all services have one.

| Property | Type | Notes |
|---|---|---|
| **SLAPolicyId** | String | PK. Format: `SLA-{NAME}-{TIER}` |
| ServiceId | String | FK → Service |
| AvailabilityPct | Double | e.g. 99.99 |
| MaxLatencyMs | Integer | |
| PenaltyPerHourUSD | Integer | |
| Tier | String | `GOLD`, `SILVER`, or `STANDARD` |

### PhysicalConduit
Duct/trench infrastructure that transport links are routed through. Multiple
links can share the same conduit — this creates shared-risk groups where
"redundant" fibres are NOT physically diverse.

| Property | Type | Notes |
|---|---|---|
| **ConduitId** | String | PK. Format: `CONDUIT-{SRC}-{DST}-{ROUTE}` |
| RouteDescription | String | Human-readable path |
| MaterialType | String | e.g. `Underground Duct` |
| InstalledYear | Integer | |

### AmplifierSite
Optical amplifiers along long-haul fibre routes (every 80–200 km). Boost
signal power between splice points. Key properties: location, calibration date.

| Property | Type | Notes |
|---|---|---|
| **SiteId** | String | PK. Format: `AMP-{SRC}-{DST}-{LOCATION}` |
| Location | String | Human-readable location |
| InstalledYear | Integer | |
| LastCalibration | Date | Check for stale calibration |
| Latitude, Longitude | Double | GPS |

### Advisory
Vendor security/bug advisories affecting specific firmware versions.

| Property | Type | Notes |
|---|---|---|
| **AdvisoryId** | String | PK. Format: `ADV-{VENDOR}-{YEAR}-{NUM}` |
| VendorName | String | |
| BugId | String | Vendor bug tracker ID |
| AffectedVersions | String | Pipe-separated firmware versions |
| Severity | String | `HIGH`, `MEDIUM`, `LOW` |
| Title | String | |
| Description | String | |

### Sensor
Physical sensors attached to infrastructure. Each has GPS for field dispatch.

| Property | Type | Notes |
|---|---|---|
| **SensorId** | String | PK. Format: `SENS-{CORRIDOR}-{TYPE}-{NUM}` |
| SensorType | String | `OpticalPower`, `BitErrorRate`, `Temperature`, `CPULoad` |
| MonitoredEntityId | String | FK → TransportLink, CoreRouter, or AmplifierSite |
| MonitoredEntityType | String | `TransportLink`, `CoreRouter`, or `AmplifierSite` |
| MountLocation | String | Human-readable where-to-find description |
| Latitude, Longitude | Double | GPS — use for dispatch destination |
| InstalledDate | String | |
| Status | String | `ACTIVE` or `INACTIVE` |

### Depot
Maintenance depots where field engineers are stationed. CityHub depots service
core routers; RegionalDepot depots service amplifier sites on inter-city corridors.

| Property | Type | Notes |
|---|---|---|
| **DepotId** | String | PK. Format: `DEPOT-{LOCATION}` |
| DepotName | String | |
| City | String | |
| Region | String | State |
| DepotType | String | `CityHub` or `RegionalDepot` |
| Latitude, Longitude | Double | GPS |
| ServicedEntityId | String | FK → CoreRouter or AmplifierSite |
| ServicedEntityType | String | `CoreRouter` or `AmplifierSite` |

### DutyRoster
On-call field engineer assignments. Searchable by city/region and shift time.

| Property | Type | Notes |
|---|---|---|
| **RosterId** | String | PK |
| PersonName | String | Full name |
| Email | String | For dispatch |
| Phone | String | For dispatch |
| City | String | |
| Region | String | |
| ShiftStart, ShiftEnd | String | ISO 8601 |
| Role | String | `FieldEngineer` (city) or `RegionalFieldEngineer` (corridor) |
| HomeBase | String | Depot location with lat/long |
| VehicleId | String | |
| DepotId | String | FK → Depot |

---

## Relationships

| Edge | Source → Target | Notes |
|---|---|---|
| `connects_to` | TransportLink → CoreRouter | Link terminates at router |
| `aggregates_to` | AggSwitch → CoreRouter | Switch uplinks to router |
| `backhauls_via` | BaseStation → AggSwitch | Base station backhauls via switch |
| `routes_via` | MPLSPath → TransportLink | MPLS path traverses link |
| `depends_on_mplspath` | Service → MPLSPath | EnterpriseVPN depends on path |
| `depends_on_aggswitch` | Service → AggSwitch | Broadband depends on switch |
| `depends_on_basestation` | Service → BaseStation | Mobile5G depends on base station |
| `governed_by` | SLAPolicy → Service | SLA governs service |
| `peers_over` | BGPSession → CoreRouter | BGP session between routers |
| `routed_through` | TransportLink → PhysicalConduit | Link runs through conduit (shared-risk detection) |
| `amplifies` | AmplifierSite → TransportLink | Amplifier boosts signal on link |
| `affects_version` | Advisory → CoreRouter | Advisory affects router firmware |
| `monitors_transportlink` | Sensor → TransportLink | Sensor observes link. **GQL: use suffixed name** |
| `monitors_corerouter` | Sensor → CoreRouter | Sensor observes router. **GQL: use suffixed name** |
| `monitors_amplifiersite` | Sensor → AmplifierSite | Sensor observes amplifier. **GQL: use suffixed name** |
| `services_corerouter` | Depot → CoreRouter | Depot maintains router. **GQL: use suffixed name** |
| `services_amplifiersite` | Depot → AmplifierSite | Depot maintains amplifier. **GQL: use suffixed name** |
| `stationed_at` | DutyRoster → Depot | Engineer stationed at depot |

### CRITICAL — disambiguated edge names in GQL

`monitors` and `services` edges are **suffixed by target type** in Fabric GQL.
Using the bare name returns **zero results**.

| Bare (WRONG) | Suffixed (CORRECT) |
|---|---|
| `monitors` | `monitors_transportlink`, `monitors_corerouter`, `monitors_amplifiersite` |
| `services` | `services_corerouter`, `services_amplifiersite` |

All other edges use their plain name unchanged.

### No direct Depot ↔ TransportLink edge

To find which depot(s) cover a transport link, traverse via intermediate nodes:
- **Via CoreRouter:** TransportLink →[connects_to]→ CoreRouter ←[services_corerouter]← Depot
- **Via AmplifierSite:** AmplifierSite →[amplifies]→ TransportLink, Depot →[services_amplifiersite]→ AmplifierSite

### Key traversal: fault → dispatch

To find the right engineer for a fault on infrastructure:
`(Infrastructure) ←[services]← (Depot) ←[stationed_at]← (DutyRoster)`