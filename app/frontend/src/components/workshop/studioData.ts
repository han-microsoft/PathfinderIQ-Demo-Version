/**
 * studioData — mock source documents + their extracted ontology fragments.
 *
 * Curated (scripted, deterministic) content for the Ontology Studio. Each doc
 * carries readable sections plus the entities/relationships an extractor would
 * pull from it. Entity `type` values and IDs mirror the real SYD–MEL topology
 * ontology so the assembled graph matches what the agents actually reason over.
 */

export interface StudioEntity {
  /** Vertex id, e.g. "LINK-SYD-MEL-FIBRE-01". */
  id: string;
  /** Ontology type / vertex label, e.g. "TransportLink". */
  type: string;
}
export interface StudioRelationship {
  source: string;
  target: string;
  /** Edge label, e.g. "routed_through". */
  type: string;
}

export interface StudioDoc {
  id: string;
  title: string;
  docType: string;
  icon: string;
  /** Short one-line description for the shelf card. */
  blurb: string;
  sections: { heading: string; body: string }[];
  entities: StudioEntity[];
  relationships: StudioRelationship[];
}

export const STUDIO_DOCS: StudioDoc[] = [
  {
    id: "doc-runbook",
    title: "NOC Runbook — SYD–MEL Corridor Fibre-Cut SOP",
    docType: "Runbook",
    icon: "📕",
    blurb: "Standard operating procedure for a corridor fibre cut.",
    sections: [
      {
        heading: "Scope",
        body:
          "Applies to loss-of-light or high-BER events on the Sydney–Melbourne " +
          "corridor carried by LINK-SYD-MEL-FIBRE-01 and LINK-SYD-MEL-FIBRE-02. " +
          "Both fibres route through CONDUIT-SYD-MEL-INLAND (Hume corridor).",
      },
      {
        heading: "Optical chain",
        body:
          "The inland conduit is amplified at AMP-SYD-MEL-GOULBURN (195 km) and " +
          "AMP-SYD-MEL-ALBURY (460 km). LINK-SYD-MEL-FIBRE-01 terminates on " +
          "CORE-SYD-01 and CORE-MEL-01.",
      },
      {
        heading: "Diversity warning",
        body:
          "FIBRE-02 is NOT physically diverse — it shares CONDUIT-SYD-MEL-INLAND. " +
          "A conduit-level cut fails both paths together.",
      },
    ],
    entities: [
      { id: "LINK-SYD-MEL-FIBRE-01", type: "TransportLink" },
      { id: "LINK-SYD-MEL-FIBRE-02", type: "TransportLink" },
      { id: "CONDUIT-SYD-MEL-INLAND", type: "PhysicalConduit" },
      { id: "AMP-SYD-MEL-GOULBURN", type: "AmplifierSite" },
      { id: "AMP-SYD-MEL-ALBURY", type: "AmplifierSite" },
      { id: "CORE-SYD-01", type: "CoreRouter" },
      { id: "CORE-MEL-01", type: "CoreRouter" },
    ],
    relationships: [
      { source: "LINK-SYD-MEL-FIBRE-01", target: "CONDUIT-SYD-MEL-INLAND", type: "routed_through" },
      { source: "LINK-SYD-MEL-FIBRE-02", target: "CONDUIT-SYD-MEL-INLAND", type: "routed_through" },
      { source: "AMP-SYD-MEL-GOULBURN", target: "LINK-SYD-MEL-FIBRE-01", type: "amplifies" },
      { source: "AMP-SYD-MEL-ALBURY", target: "LINK-SYD-MEL-FIBRE-01", type: "amplifies" },
      { source: "LINK-SYD-MEL-FIBRE-01", target: "CORE-SYD-01", type: "connects_source" },
      { source: "LINK-SYD-MEL-FIBRE-01", target: "CORE-MEL-01", type: "connects_target" },
    ],
  },
  {
    id: "doc-sla",
    title: "Enterprise SLA — ACME Corp Managed VPN Agreement",
    docType: "SLA Contract",
    icon: "📜",
    blurb: "Contract terms + penalty schedule for the ACME enterprise VPN.",
    sections: [
      {
        heading: "Service",
        body:
          "This agreement governs VPN-ACME-CORP, an enterprise VPN service " +
          "delivered over the Sydney–Melbourne corridor.",
      },
      {
        heading: "Service level (SLA-ACME-GOLD)",
        body:
          "Availability target 99.95%. Under SLA-ACME-GOLD the PenaltyPerHourUSD " +
          "for a service-affecting outage is $45,000/hour.",
      },
      {
        heading: "Dependencies",
        body:
          "VPN-ACME-CORP depends on LINK-SYD-MEL-FIBRE-01 as its primary path.",
      },
    ],
    entities: [
      { id: "SLA-ACME-GOLD", type: "SLAPolicy" },
      { id: "VPN-ACME-CORP", type: "Service" },
    ],
    relationships: [
      { source: "SLA-ACME-GOLD", target: "VPN-ACME-CORP", type: "governs" },
      { source: "VPN-ACME-CORP", target: "LINK-SYD-MEL-FIBRE-01", type: "depends_on" },
    ],
  },
  {
    id: "doc-cmdb",
    title: "Network Inventory — CMDB Export (Sydney North)",
    docType: "Inventory",
    icon: "🗄️",
    blurb: "Configuration-management export of core + access devices.",
    sections: [
      {
        heading: "Core / aggregation",
        body:
          "CORE-SYD-01 (Cisco ASR-9922) and CORE-MEL-01 anchor the corridor. " +
          "AGG-SYD-NORTH-01 aggregates the northern access ring and uplinks to " +
          "CORE-SYD-01.",
      },
      {
        heading: "5G access",
        body:
          "Base stations GNB-SYD-2041 and GNB-SYD-2042 backhaul via " +
          "AGG-SYD-NORTH-01.",
      },
    ],
    entities: [
      { id: "CORE-SYD-01", type: "CoreRouter" },
      { id: "CORE-MEL-01", type: "CoreRouter" },
      { id: "AGG-SYD-NORTH-01", type: "AggSwitch" },
      { id: "GNB-SYD-2041", type: "BaseStation" },
      { id: "GNB-SYD-2042", type: "BaseStation" },
    ],
    relationships: [
      { source: "AGG-SYD-NORTH-01", target: "CORE-SYD-01", type: "uplinks_to" },
      { source: "GNB-SYD-2041", target: "AGG-SYD-NORTH-01", type: "backhauls_via" },
      { source: "GNB-SYD-2042", target: "AGG-SYD-NORTH-01", type: "backhauls_via" },
    ],
  },
  {
    id: "doc-survey",
    title: "Fibre Route Survey — Hume Inland Corridor",
    docType: "Fibre Survey",
    icon: "🗺️",
    blurb: "Physical conduit route + amplifier hut GPS coordinates.",
    sections: [
      {
        heading: "Conduit route",
        body:
          "CONDUIT-SYD-MEL-INLAND runs Sydney→Melbourne via the Hume Highway " +
          "through the Southern Highlands.",
      },
      {
        heading: "Amplifier huts",
        body:
          "AMP-SYD-MEL-GOULBURN at Goulburn NSW (−34.7546, 149.7186) and " +
          "AMP-SYD-MEL-ALBURY at Albury NSW amplify the inland span.",
      },
    ],
    entities: [
      { id: "CONDUIT-SYD-MEL-INLAND", type: "PhysicalConduit" },
      { id: "AMP-SYD-MEL-GOULBURN", type: "AmplifierSite" },
      { id: "AMP-SYD-MEL-ALBURY", type: "AmplifierSite" },
    ],
    relationships: [
      { source: "AMP-SYD-MEL-GOULBURN", target: "CONDUIT-SYD-MEL-INLAND", type: "routed_through" },
      { source: "AMP-SYD-MEL-ALBURY", target: "CONDUIT-SYD-MEL-INLAND", type: "routed_through" },
    ],
  },
  {
    id: "doc-depot",
    title: "Field Ops — Depot & Duty Roster (Goulburn)",
    docType: "Depot Roster",
    icon: "🧑‍🔧",
    blurb: "Servicing depot + on-call engineer roster for the corridor.",
    sections: [
      {
        heading: "Depot",
        body:
          "DEPOT-GOULBURN services the Goulburn span, including " +
          "AMP-SYD-MEL-GOULBURN.",
      },
      {
        heading: "Roster",
        body:
          "ROSTER-GOULBURN-A lists the on-call field engineers stationed at " +
          "DEPOT-GOULBURN.",
      },
    ],
    entities: [
      { id: "DEPOT-GOULBURN", type: "Depot" },
      { id: "ROSTER-GOULBURN-A", type: "DutyRoster" },
    ],
    relationships: [
      { source: "DEPOT-GOULBURN", target: "AMP-SYD-MEL-GOULBURN", type: "services" },
      { source: "ROSTER-GOULBURN-A", target: "DEPOT-GOULBURN", type: "stationed_at" },
    ],
  },
  {
    id: "doc-mpls",
    title: "MPLS Path & Service Design — SYD–MEL",
    docType: "Service Design",
    icon: "🧭",
    blurb: "Engineered label-switched paths and the services riding them.",
    sections: [
      {
        heading: "Primary path",
        body:
          "MPLS-PATH-SYD-MEL-PRIMARY traverses CORE-SYD-01 and CORE-MEL-01, " +
          "carried over LINK-SYD-MEL-FIBRE-01.",
      },
      {
        heading: "Diverse path",
        body:
          "MPLS-PATH-SYD-MEL-VIA-BNE traverses CORE-SYD-01 and routes via " +
          "Brisbane — the only truly diverse option off the inland corridor.",
      },
      {
        heading: "Service mapping",
        body: "VPN-BIGBANK depends on MPLS-PATH-SYD-MEL-PRIMARY as its committed path.",
      },
    ],
    entities: [
      { id: "MPLS-PATH-SYD-MEL-PRIMARY", type: "MPLSPath" },
      { id: "MPLS-PATH-SYD-MEL-VIA-BNE", type: "MPLSPath" },
      { id: "VPN-BIGBANK", type: "Service" },
    ],
    relationships: [
      { source: "MPLS-PATH-SYD-MEL-PRIMARY", target: "CORE-SYD-01", type: "traverses" },
      { source: "MPLS-PATH-SYD-MEL-PRIMARY", target: "CORE-MEL-01", type: "traverses" },
      { source: "MPLS-PATH-SYD-MEL-VIA-BNE", target: "CORE-SYD-01", type: "traverses" },
      { source: "VPN-BIGBANK", target: "MPLS-PATH-SYD-MEL-PRIMARY", type: "depends_on" },
    ],
  },
  {
    id: "doc-bgp",
    title: "BGP Peering Register — Corridor Core",
    docType: "Routing Config",
    icon: "🔗",
    blurb: "iBGP sessions between the corridor's core routers.",
    sections: [
      {
        heading: "Session",
        body: "BGP-SYD-MEL-01 peers CORE-SYD-01 with CORE-MEL-01 (iBGP, AS 64500).",
      },
      {
        heading: "Role",
        body:
          "This session exchanges the routes that keep VPN-ACME-CORP and " +
          "VPN-BIGBANK reachable across the corridor.",
      },
    ],
    entities: [{ id: "BGP-SYD-MEL-01", type: "BGPSession" }],
    relationships: [
      { source: "BGP-SYD-MEL-01", target: "CORE-SYD-01", type: "peers" },
      { source: "BGP-SYD-MEL-01", target: "CORE-MEL-01", type: "peers" },
    ],
  },
  {
    id: "doc-telemetry",
    title: "Telemetry & Change Register — Inland Span",
    docType: "Ops Register",
    icon: "📡",
    blurb: "Optical sensors on the span plus an open change advisory.",
    sections: [
      {
        heading: "Sensors",
        body:
          "SENSOR-SYD-MEL-045 (45 km) and SENSOR-SYD-MEL-195 (195 km) monitor " +
          "LINK-SYD-MEL-FIBRE-01 for optical power and bit-error rate.",
      },
      {
        heading: "Change advisory",
        body:
          "ADV-2026-014 is an open maintenance advisory that affects CORE-SYD-01 " +
          "during this weekend's window.",
      },
    ],
    entities: [
      { id: "SENSOR-SYD-MEL-045", type: "Sensor" },
      { id: "SENSOR-SYD-MEL-195", type: "Sensor" },
      { id: "ADV-2026-014", type: "Advisory" },
    ],
    relationships: [
      { source: "SENSOR-SYD-MEL-045", target: "LINK-SYD-MEL-FIBRE-01", type: "monitors" },
      { source: "SENSOR-SYD-MEL-195", target: "LINK-SYD-MEL-FIBRE-01", type: "monitors" },
      { source: "ADV-2026-014", target: "CORE-SYD-01", type: "affects" },
    ],
  },
];

/** One-line definition per entity type — shown in the schema + detail panels. */
export const ENTITY_TYPE_INFO: Record<string, string> = {
  CoreRouter: "Backbone router switching traffic between metro regions.",
  AggSwitch: "Aggregation switch concentrating access traffic onto the core.",
  BaseStation: "5G gNodeB radio site providing mobile coverage.",
  TransportLink: "Logical DWDM link carrying traffic between core routers.",
  PhysicalConduit: "Underground duct that physically carries the fibre pairs.",
  AmplifierSite: "Inline optical amplifier hut boosting signal along a span.",
  Service: "A customer-facing service (enterprise VPN, broadband, mobile).",
  SLAPolicy: "Contractual service-level policy with penalty terms.",
  MPLSPath: "An engineered MPLS label-switched path across the network.",
  BGPSession: "A BGP peering session exchanging routes between routers.",
  Advisory: "An operational change or maintenance advisory.",
  Sensor: "An optical / telemetry sensor monitoring a span or device.",
  Depot: "A field-operations depot servicing a region.",
  DutyRoster: "An on-call roster of field engineers at a depot.",
};

/** One-line definition per relationship type. */
export const REL_TYPE_INFO: Record<string, string> = {
  routed_through: "A transport link physically traverses a conduit.",
  amplifies: "An amplifier site boosts a transport link's signal.",
  connects_source: "A transport link originates at a core router.",
  connects_target: "A transport link terminates at a core router.",
  governs: "An SLA policy governs a customer service.",
  depends_on: "A service depends on an underlying network element.",
  uplinks_to: "An aggregation switch uplinks to a core router.",
  backhauls_via: "A base station backhauls via an aggregation switch.",
  services: "A depot services a physical site.",
  stationed_at: "A duty roster is stationed at a depot.",
  peers: "A BGP session peers with a core router.",
  traverses: "An MPLS path traverses a network node.",
  affects: "An advisory affects a network element.",
  monitors: "A sensor monitors a network element.",
};

/** Sample properties per entity — shown in the entity detail card. */
export const ENTITY_PROPS: Record<string, Record<string, string>> = {
  "CORE-SYD-01": { Vendor: "Cisco", Model: "ASR-9922", City: "Sydney", Firmware: "IOS-XR 7.9.2" },
  "CORE-MEL-01": { Vendor: "Cisco", Model: "ASR-9922", City: "Melbourne" },
  "LINK-SYD-MEL-FIBRE-01": { Type: "DWDM 100G", Capacity: "100 Gbps", Status: "primary" },
  "LINK-SYD-MEL-FIBRE-02": { Type: "DWDM 100G", Capacity: "100 Gbps", Status: "secondary" },
  "CONDUIT-SYD-MEL-INLAND": { Route: "Hume Hwy / Goulburn", Span: "≈ 880 km" },
  "AMP-SYD-MEL-GOULBURN": { Location: "Goulburn NSW", Distance: "195 km", GPS: "-34.7546, 149.7186" },
  "AMP-SYD-MEL-ALBURY": { Location: "Albury NSW", Distance: "460 km" },
  "SLA-ACME-GOLD": { Tier: "Gold", Availability: "99.95%", "Penalty / hr": "$45,000" },
  "VPN-ACME-CORP": { Customer: "ACME Corp", Type: "Enterprise VPN", Users: "1,200" },
  "VPN-BIGBANK": { Customer: "BigBank", Type: "Enterprise VPN", Users: "900" },
  "AGG-SYD-NORTH-01": { Role: "Aggregation", Region: "Sydney North" },
  "GNB-SYD-2041": { Type: "5G NR", City: "Sydney" },
  "GNB-SYD-2042": { Type: "5G NR", City: "Sydney" },
  "MPLS-PATH-SYD-MEL-PRIMARY": { Role: "Primary", Diverse: "No (shares inland conduit)" },
  "MPLS-PATH-SYD-MEL-VIA-BNE": { Role: "Diverse backup", Via: "Brisbane" },
  "BGP-SYD-MEL-01": { Protocol: "iBGP", AS: "64500" },
  "ADV-2026-014": { Type: "Planned maintenance", Window: "Sat 02:00–04:00" },
  "SENSOR-SYD-MEL-195": { Reads: "Optical power, BER", At: "195 km" },
  "SENSOR-SYD-MEL-045": { Reads: "Optical power, BER", At: "45 km" },
  "DEPOT-GOULBURN": { Region: "Goulburn", Equipment: "OTDR, splicer" },
};
