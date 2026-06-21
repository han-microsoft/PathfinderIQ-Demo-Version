# Open Telco Datasets for a GridIQ-Style "Autonomous Network" Demo

Research note — candidate **open / public** datasets to power a genericized, telco-flavoured
agent demo (PathfinderIQ). Goal: show the flavour of an **autonomous telecom network** across the
same four surfaces GridIQ uses — **telemetry, alarms, knowledge base, graph** — ideally in one
coherent, join-able package.

Last researched: 2026-06-19. Links verified live at research time; always re-check the licence on
the source page before redistribution.

> **STATUS NOTE (2026-06-21):** This is a historical research note, not current demo content.
> The O-RAN option discussed below (ColO-RAN / OpenRAN Gym, "Option 1") was evaluated, briefly
> onboarded as a scenario pack, then **removed from the live PathfinderIQ demo** when the focus
> narrowed to the Sydney–Melbourne fibre-cut telecom scenario for the C-suite walkthrough. Keep
> this file for dataset-evaluation reference only; it does not reflect what ships today. See
> AUTODEV.md for the rationale.

---

## TL;DR verdict

- **No single open telco dataset ships all four surfaces with native joins** the way PSML does for
  power grid. (PSML is unusually lucky; telco's hard joins aren't pre-solved for you.)
- **The "autonomous network" flavour comes from the closed control loop**, not from a 4-surface
  data dump. So pick a spine that ships the *act* leg (RIC/xApp control), then bolt on the missing
  surfaces with the same synthesize-at-the-boundary pattern GridIQ already uses for alarms.
- **Two recommended spines:**
  1. **O-RAN closed loop (ColO-RAN / OpenRAN Gym)** — the only open set with the *act* leg (RIC
     xApp control). Reads as a genuine "self-driving network." **Best for the autonomous flavour.**
  2. **Network digital twin (RouteNet / GNNet Challenge)** — native graph↔telemetry join, framed
     explicitly as a network digital twin. **Best for a clean graph + twin pitch.**
- **Most coherent single all-four package** (telco-adjacent, not RAN): **GAIA** microservice AIOps
  set — metrics + traces(graph) + logs + anomaly-injection labels, all keyed on `service_name`.
- **Telco beats grid on the knowledge base**: real, large, public 3GPP/O-RAN RAG corpora exist
  (TeleQnA, TSpec-LLM).

---

## How these map to the four demo surfaces

| Demo surface | What it is in the app | What a telco dataset must provide |
|---|---|---|
| **Topology / graph** | Gremlin/CIM-style graph (`graph_*` tools): network elements + relationships | gNB/cell/slice/UE hierarchy, link/queue topology, or cell-tower geo |
| **Telemetry time-series** | KPI/KPM streams behind the KQL adapter | timestamped per-element measurements (throughput, PRB, delay, jitter, loss) |
| **Alarms / events** | situation detector + alarm rows | discrete fault/SLA-breach records with timestamp + affected element |
| **Knowledge base (RAG)** | AI Search indexes | free-text specs / runbooks / Q&A to embed + retrieve |
| **(bonus) Action / act leg** | agent closes the loop | a control decision (scheduling policy, slice config) the agent can recommend/justify |

> The **act leg** is what a power-grid demo cannot easily show and an O-RAN demo can — the agent
> doesn't just detect, it closes the loop. That is the autonomous-network money shot.

---

## OPTION 1 — O-RAN closed loop (recommended for the autonomous flavour)

**OpenRAN Gym + ColO-RAN dataset** — Northeastern University WINES Lab.

- **Links:**
  - OpenRAN Gym: https://openrangym.com/ · datasets index: https://openrangym.com/datasets
  - ColO-RAN dataset: https://github.com/wineslab/colosseum-oran-coloran-dataset
- **Licence:** GPL-3.0 (ColO-RAN repo). Verify per-file before redistribution.
- **What:** A publicly available O-RAN research platform — near-real-time RIC + E2 termination +
  ML **xApps** performing closed-loop RAN control. The dataset is the observe→decide→act loop.
- **ColO-RAN experiment slice (verified):** 7 base stations; 3 slices per BS (eMBB / MTC / URLLC);
  42 UEs; 3 schedulers (round-robin / waterfilling / proportionally-fair); per-slice **KPM
  time-series** across many Resource Block Group allocations.
- **Surface mapping:**
  - **Telemetry** = per-slice / per-UE KPMs (throughput, PRB usage, buffer, MCS).
  - **Graph** = `gNB → slice → UE` hierarchy + cell adjacency. Native keys (BS id, slice id, UE id).
  - **Alarms** = derive from KPM breaches (URLLC latency SLA, PRB starvation) — synthesize
    categorical rows at the tool boundary (same pattern GridIQ uses for grid alarms).
  - **Action** = the xApp scheduling-policy switch. The agent recommends + justifies it = closed loop.
  - **Knowledge base** = O-RAN WG specs + 3GPP (public).
- **Caveat:** RAN testbed (Colosseum-emulated), not a live carrier. Demo-grade, honestly labelled.

---

## OPTION 2 — Network digital twin (recommended for a clean graph + twin pitch)

**Graph Neural Networking Challenge / RouteNet** — Barcelona Neural Networking Center (BNN-UPC).

- **Links:**
  - Challenge hub: https://bnn.upc.edu/challenge/
  - 2023 (Network Digital Twin, real data): https://bnn.upc.edu/challenge/gnnet2023/
  - 2021 (scalable twin): https://bnn.upc.edu/challenge/gnnet2021/
  - Datasets / code: https://github.com/BNN-UPC
- **Licence:** per-edition (open, research). Check the specific edition page.
- **What:** Annual GNN-for-networking competition. Datasets ship a **network digital twin**:
  topology + traffic + resulting QoS, designed to predict the network's own behaviour.
- **Native graph↔telemetry join:** topology (nodes / links / queues) + per-source-destination
  **traffic matrix** + per-path **delay / jitter / loss**. One topology id threads
  graph → traffic → QoS. This is the hard join, solved natively.
- **Surface mapping:**
  - **Graph** = network topology (nodes, links, queue scheduling policies).
  - **Telemetry** = per-path delay / jitter / loss + traffic matrix.
  - **Alarms** = synthesize from SLA-violating paths.
  - **Knowledge base** = RFCs / QoS specs.
- **Caveat:** no native alarms or KB; strongest on graph + telemetry. Framing ("digital twin") is
  itself the autonomous-network story.

---

## Most coherent single all-four package (telco-adjacent)

**GAIA (Generic AIOps Atlas)** — CloudWise.

- **Link:** https://github.com/CloudWise-OpenSource/GAIA-DataSet
- **Licence:** Apache-2.0 (verified).
- **What:** One microservice scenario (`MicroSS`, QR-login) shipping all four surfaces, **natively
  join-able on `service_name` / `host_ip`**: 6,500+ metric series; OpenTracing traces with
  `trace_id/span_id/parent_id`; system + business logs; explicit **anomaly-injection records**.
- **Surface mapping:**
  - **Telemetry** = `metric/` KPI series.
  - **Graph** = derive the service-call graph from `trace/` spans (parent/child).
  - **Alarms** = `run/` anomaly-injection records (e.g. `[memory_anomalies] ... lasts 600s`),
    time-aligned to the metrics.
  - **Knowledge base** = log / NER corpus.
- **Why it matters:** the crown-jewel join (telemetry↔alarms↔graph) is free, exactly like PSML for
  grid. **Caveat:** it's IT/microservice ops (what telco NOCs run on), not RAN/core — "telco" only
  in the AIOps sense. V1.10 omitted some trace data; confirm trace coverage for the month you pick.

---

## Surface-by-surface telco-native picks (for a stitched stack)

| Surface | Source | Link | Note |
|---|---|---|---|
| Telemetry | ColO-RAN KPMs | https://github.com/wineslab/colosseum-oran-coloran-dataset | per-slice/UE RAN KPIs |
| Telemetry | RouteNet per-path QoS | https://bnn.upc.edu/challenge/ | delay/jitter/loss, native graph key |
| Telemetry | SNDlib dynamic traffic matrices | https://sndlib.put.poznan.pl/ | real measured matrices on real topologies |
| Telemetry | Telecom Italia "Big Data Challenge" (Milano) | https://dandelion.eu/datamine/open-big-data/ | geospatial CDR (SMS/call/internet activity) |
| Graph | ColO-RAN gNB/slice/UE | (above) | native experiment config |
| Graph | RouteNet topology | https://bnn.upc.edu/challenge/ | nodes/links/queues |
| Graph | SNDlib (GÉANT, Nobel, etc.) | https://sndlib.put.poznan.pl/ | real telco topologies + traffic |
| Graph | Internet Topology Zoo | http://www.topology-zoo.org/ | 261 real ISP topologies (GraphML) |
| Graph | OpenCelliD (cell-tower geo) | https://opencellid.org/ | world's largest open cell-tower DB → spatial RAN graph |
| Alarms | **synthesize** from KPM/SLA breach | — | no clean non-CEII open carrier alarm log exists |
| Alarms tooling | Orange SSAD (self-supervised anomaly detection) | https://github.com/Orange-OpenSource/SSAD | MIT; pairs with alarm synthesis |
| Knowledge base | TeleQnA (3GPP Q&A) | https://github.com/netop-team/TeleQnA | telco-specific RAG corpus |
| Knowledge base | TSpec-LLM (3GPP spec corpus) | https://huggingface.co/datasets/rasoul-nikbakht/TSpec-LLM | large 3GPP text corpus |
| Knowledge base | O-RAN Alliance specs | https://www.o-ran.org/specifications | public WG specifications |
| Knowledge base | 3GPP specifications | https://www.3gpp.org/specifications | canonical telecom standards |

---

## Recommended "starter stack" (one per surface)

A complete, telco-native, autonomous-flavoured stack centred on the O-RAN closed loop:

| Surface | Pick | Licence | Why |
|---|---|---|---|
| Telemetry + act leg | **ColO-RAN / OpenRAN Gym** | GPL-3.0 | only open set with RIC xApp control loop |
| Graph | **ColO-RAN gNB/slice/UE** (+ OpenCelliD for geo map) | GPL-3.0 / community | native keys; cell geo for a map surface |
| Alarms | **synthesize** from URLLC/eMBB SLA breach (+ Orange SSAD) | n/a / MIT | clean data-boundary by construction |
| Knowledge base | **TeleQnA + TSpec-LLM + O-RAN/3GPP specs** | open | telco's strongest surface — real public corpus |

Alternative (digital-twin pitch): swap the spine to **RouteNet/GNNet** for native graph↔telemetry,
synthesize alarms from SLA-violating paths, keep the same KB.

---

## Honest caveats / things to verify before committing

- `unknown:` **5G3E** (Orange 5G end-to-end emulation: infra + network + app metrics + logs) is a
  strong multi-layer **5G-core** candidate, but a live canonical repo URL was not confirmed this
  pass. Worth a targeted hunt if you want a 5G-core (not RAN) flavour.
- **No open non-CEII carrier alarm log.** Alarms must be synthesized from telemetry/SLA breaches —
  same posture GridIQ already takes (categorical projection at the tool boundary).
- **Licences vary per surface.** ColO-RAN = GPL-3.0, GAIA = Apache-2.0, GNNet = per-edition,
  SNDlib/Topology Zoo = research-use. Re-check redistribution clauses before shipping a demo.
- **Data boundary still applies.** Keep raw element identifiers out of agent-visible envelopes;
  return categorical/synthetic projections, embed prose in the RAG index for retrieval only.
- **Demo-grade, honestly labelled.** ColO-RAN is Colosseum-emulated; RouteNet is simulated; GAIA is
  injected faults. All are fine for an accelerator *demo*, not for carrier-fidelity benchmarks.

---

## Bottom line

- **Want the autonomous "self-driving network" flavour:** build on **ColO-RAN / OpenRAN Gym**. It
  ships the act leg (RIC xApp closed loop) no other open telco set offers. Telemetry from KPMs,
  graph from `gNB→slice→UE`, alarms synthesized from SLA breach, KB from O-RAN/3GPP, agent
  recommends + justifies a scheduling-policy switch = closed loop.
- **Want a clean graph + digital-twin pitch:** **RouteNet / GNNet** with **OpenCelliD** for a cell map.
- **Want the most coherent single 4-surface package today:** **GAIA**, accepting it's IT/microservice
  ops rather than RAN/core.
- **The KB surface is where telco wins** — TeleQnA / TSpec-LLM / 3GPP give a real, large, public
  corpus the grid demo never had.

*Doc-only research note. No code, no deploy. Links verified 2026-06-19.*
