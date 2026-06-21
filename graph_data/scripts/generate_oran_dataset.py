#!/usr/bin/env python3
"""Deterministic synthetic-data generator for the O-RAN 5G RAN scenario pack.

Emits a structurally-faithful (ColO-RAN-shaped) 5G RAN dataset — demo-grade,
honestly synthetic — across all three PathfinderIQ data surfaces:

  graph (Cosmos Gremlin)  : gNB → CU → DU → Cell hierarchy, network slices,
                            UE cohorts, SLA policies, fronthaul/midhaul/backhaul
                            transport links.  -> data/entities/*.csv
  telemetry (Cosmos NoSQL): per-slice / per-cell / per-UE KPM time series and a
                            synthesised alarm stream.            -> data/telemetry/*.csv

INCIDENT BATTERY — six independent incidents across distinct event classes and
sites, plus benign baseline (PTP clock drift). This makes the pack a multi-class
evaluation battery (see graph_data/eval/), not a single demo:

  1. fronthaul_degradation -> URLLC SLA breach   (GNB-MEL-01 / DU-MEL-01-2)  CRITICAL
  2. pci_collision (RRC, no transport fault)     (GNB-SYD-01 / CELL-SYD-01-1-1) MAJOR
  3. midhaul_congestion (whole-DU, even)         (GNB-BNE-01 / DU-BNE-01-1)   SERIOUS
  4. mmtc_signaling_storm (slice isolation holds)(GNB-PER-01 / SL-MMTC-01)    MAJOR
  5. backhaul_flap (intermittent whole-gNB)      (GNB-SYD-02 backhaul)        SERIOUS
  6. demand_congestion (no fault; carrier-agg)   (GNB-BNE-02 / CELL-BNE-02-1-2) SERIOUS

Run:
    python3 graph_data/scripts/generate_oran_dataset.py
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "oran-5g-ran"
ENT = PACK / "data" / "entities"
TEL = PACK / "data" / "telemetry"

RNG = random.Random(424242)

CITIES = [
    ("SYD", "Sydney", "NSW", -33.8688, 151.2093),
    ("MEL", "Melbourne", "VIC", -37.8136, 144.9631),
    ("BNE", "Brisbane", "QLD", -27.4698, 153.0251),
    ("PER", "Perth", "WA", -31.9505, 115.8605),
]
VENDORS = [("Ericsson", "AIR-6488"), ("Nokia", "AirScale-ASIR"),
           ("Samsung", "vRAN-3.0"), ("Mavenir", "OpenBeam-OB-78")]
BANDS = [("n78", 3500, 273), ("n28", 700, 106), ("n258", 26000, 132)]

# Slices (global). (SliceId, SST, SNSSAI, SLA latency ms, SLA tput Mbps, tenant, tier, penalty/hr)
SLICES = [
    ("SL-EMBB-01", "eMBB", "01-000001", 20, 100, "ConsumerMBB", "SILVER", 1500),
    ("SL-URLLC-01", "URLLC", "02-000001", 5, 50, "SmartGridCo", "GOLD", 5000),
    ("SL-MMTC-01", "mMTC", "03-000001", 100, 1, "MeteringIoT", "STANDARD", 300),
    ("SL-EMBB-02", "eMBB", "01-000002", 25, 80, "StadiumVideo", "SILVER", 1800),
    ("SL-URLLC-02", "URLLC", "02-000002", 8, 40, "RoboticsAU", "GOLD", 4200),
    ("SL-MMTC-02", "mMTC", "03-000002", 120, 1, "FleetTelematics", "STANDARD", 250),
]

# Time window: 24 samples, 5-min cadence.
T0 = datetime(2025, 6, 21, 8, 0, 0, tzinfo=timezone.utc)
N_SAMPLES = 24

# ── Incident registry (declarative; resolved against entities below) ─────────
# kind ∈ {fronthaul, pci, midhaul, mmtc, backhaul, demand}. Targets matched by
# gnb / du / explicit cells / slice. onset..end are sample indices.
INCIDENTS = [
    {"id": "fronthaul-urllc", "kind": "fronthaul", "gnb": "GNB-MEL-01",
     "du": "DU-MEL-01-2", "slice": "SL-URLLC-01", "onset": 14, "end": 24},
    {"id": "pci-collision", "kind": "pci", "gnb": "GNB-SYD-01",
     "cells": ["CELL-SYD-01-1-1"], "onset": 4, "end": 11},
    {"id": "midhaul-congestion", "kind": "midhaul", "gnb": "GNB-BNE-01",
     "du": "DU-BNE-01-1", "onset": 8, "end": 17, "link": "LINK-MH-DU-BNE-01-1"},
    {"id": "mmtc-signaling-storm", "kind": "mmtc", "gnb": "GNB-PER-01",
     "slice": "SL-MMTC-01", "onset": 10, "end": 19},
    {"id": "backhaul-flap", "kind": "backhaul", "gnb": "GNB-SYD-02",
     "onset": 6, "end": 21, "link": "LINK-BH-GNB-SYD-02"},
    {"id": "demand-congestion", "kind": "demand", "gnb": "GNB-BNE-02",
     "cells": ["CELL-BNE-02-1-2"], "onset": 12, "end": 23},
]


def ts(i: int) -> str:
    return (T0 + timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})
    print(f"  {path.relative_to(PACK)}: {len(rows)} rows")


# ── Build topology ──────────────────────────────────────────────────────────
core = {"CoreId": "CORE-AU-5GC", "Name": "National 5G Core", "Region": "AU",
        "NSSF": "active", "AMF": "active", "Latitude": -33.8688, "Longitude": 151.2093}

gnbs, cus, dus, cells, ues, links = [], [], [], [], [], []
cell_slice = []
slapolicies = []

for ci, (code, city, region, lat, lon) in enumerate(CITIES):
    for g in range(1, 3):
        gnb_id = f"GNB-{code}-{g:02d}"
        vendor, model = VENDORS[(ci + g) % len(VENDORS)]
        jlat = round(lat + RNG.uniform(-0.05, 0.05), 5)
        jlon = round(lon + RNG.uniform(-0.05, 0.05), 5)
        gnbs.append({"gNBId": gnb_id, "Name": f"{city} gNB {g}", "City": city,
                     "Region": region, "Vendor": vendor, "Model": model,
                     "Latitude": jlat, "Longitude": jlon})
        cu_id = f"CU-{code}-{g:02d}"
        cus.append({"CUId": cu_id, "gNBId": gnb_id, "CUType": "CU-CP+UP",
                    "SoftwareVersion": f"oran-cu-{2 + (ci % 3)}.{g}.1"})
        links.append({"LinkId": f"LINK-BH-{gnb_id}", "LinkType": "BACKHAUL_N3",
                      "SourceId": gnb_id, "TargetId": core["CoreId"], "CapacityGbps": 25,
                      "MediaType": "Fibre"})
        for d in range(1, 3):
            du_id = f"DU-{code}-{g:02d}-{d}"
            dus.append({"DUId": du_id, "gNBId": gnb_id, "CUId": cu_id,
                        "Numerology": "mu1-30kHz", "MaxLayers": 4})
            links.append({"LinkId": f"LINK-MH-{du_id}", "LinkType": "MIDHAUL_F1",
                          "SourceId": cu_id, "TargetId": du_id, "CapacityGbps": 10,
                          "MediaType": "Fibre"})
            for c in range(1, 4):
                band, freq, maxprb = BANDS[(d + c) % len(BANDS)]
                cell_id = f"CELL-{code}-{g:02d}-{d}-{c}"
                pci = (ci * 64 + g * 16 + d * 4 + c) % 504
                cells.append({"CellId": cell_id, "DUId": du_id, "Band": band,
                              "FreqMHz": freq, "PCI": pci, "AzimuthDeg": (c * 120) % 360,
                              "MaxPRB": maxprb})
                links.append({"LinkId": f"LINK-FH-{cell_id}", "LinkType": "FRONTHAUL_eCPRI",
                              "SourceId": du_id, "TargetId": cell_id, "CapacityGbps": 25,
                              "MediaType": "DarkFibre"})
                assigned = ["SL-EMBB-01"]
                if c == 1:
                    assigned.append("SL-URLLC-01" if d == 2 else "SL-URLLC-02")
                if c == 2:
                    assigned.append("SL-MMTC-01")
                if c == 3:
                    assigned.append("SL-EMBB-02")
                if (ci + g) % 2 == 0 and c == 2:
                    assigned.append("SL-MMTC-02")
                for s in assigned:
                    cell_slice.append({"CellId": cell_id, "SliceId": s})
                for k, s in enumerate(assigned[:2], start=1):
                    ue_id = f"UE-{cell_id}-{k}"
                    sst = next(x for x in SLICES if x[0] == s)[1]
                    dc = {"eMBB": "Smartphone", "URLLC": "IndustrialController",
                          "mMTC": "IoTModule"}[sst]
                    subs = {"eMBB": RNG.randint(120, 480),
                            "URLLC": RNG.randint(8, 40),
                            "mMTC": RNG.randint(800, 3000)}[sst]
                    ues.append({"UEId": ue_id, "CellId": cell_id, "SliceId": s,
                                "DeviceClass": dc, "SubscriberCount": subs})

for sid, sst, snssai, lat_ms, tput, tenant, tier, penalty in SLICES:
    slapolicies.append({"SLAPolicyId": f"SLAP-{sid}", "SliceId": sid,
                        "MaxLatencyMs": lat_ms, "MinThroughputMbps": tput,
                        "PenaltyPerHourUSD": penalty, "Tier": tier})

slices_rows = [{"SliceId": s[0], "SST": s[1], "SNSSAI": s[2], "SLALatencyMs": s[3],
                "SLAThroughputMbps": s[4], "TenantName": s[5]} for s in SLICES]

# ── Resolve incident targets against entities ────────────────────────────────
cells_by_du: dict[str, list[str]] = {}
cells_by_gnb: dict[str, list[str]] = {}
du_gnb = {d["DUId"]: d["gNBId"] for d in dus}
for cl in cells:
    cells_by_du.setdefault(cl["DUId"], []).append(cl["CellId"])
    cells_by_gnb.setdefault(du_gnb[cl["DUId"]], []).append(cl["CellId"])
ues_by_cell: dict[str, list[str]] = {}
for u in ues:
    ues_by_cell.setdefault(u["CellId"], []).append(u["UEId"])

for inc in INCIDENTS:
    tcells: list[str] = list(inc.get("cells", []))
    if inc.get("du"):
        tcells = cells_by_du.get(inc["du"], [])
    elif inc["kind"] == "backhaul":
        tcells = cells_by_gnb.get(inc["gnb"], [])
    inc["_cells"] = set(tcells)

cell_incident: dict[str, dict] = {}
for inc in INCIDENTS:
    for cid in inc["_cells"]:
        cell_incident.setdefault(cid, inc)  # sites disjoint; first wins
slice_incident = {inc["slice"]: inc for inc in INCIDENTS if inc.get("slice")}

# ── Write entity CSVs ────────────────────────────────────────────────────────
print("Entities:")
write_csv(ENT / "DimCoreNetwork.csv",
          ["CoreId", "Name", "Region", "NSSF", "AMF", "Latitude", "Longitude"], [core])
write_csv(ENT / "DimGNB.csv",
          ["gNBId", "Name", "City", "Region", "Vendor", "Model", "Latitude", "Longitude"], gnbs)
write_csv(ENT / "DimCU.csv", ["CUId", "gNBId", "CUType", "SoftwareVersion"], cus)
write_csv(ENT / "DimDU.csv", ["DUId", "gNBId", "CUId", "Numerology", "MaxLayers"], dus)
write_csv(ENT / "DimCell.csv",
          ["CellId", "DUId", "Band", "FreqMHz", "PCI", "AzimuthDeg", "MaxPRB"], cells)
write_csv(ENT / "DimSlice.csv",
          ["SliceId", "SST", "SNSSAI", "SLALatencyMs", "SLAThroughputMbps", "TenantName"], slices_rows)
write_csv(ENT / "DimSLAPolicy.csv",
          ["SLAPolicyId", "SliceId", "MaxLatencyMs", "MinThroughputMbps",
           "PenaltyPerHourUSD", "Tier"], slapolicies)
write_csv(ENT / "DimUE.csv",
          ["UEId", "CellId", "SliceId", "DeviceClass", "SubscriberCount"], ues)
write_csv(ENT / "DimTransportLink.csv",
          ["LinkId", "LinkType", "SourceId", "TargetId", "CapacityGbps", "MediaType"], links)
write_csv(ENT / "FactCellSlice.csv", ["CellId", "SliceId"], cell_slice)

# ── Telemetry ────────────────────────────────────────────────────────────────
print("Telemetry:")


def ramp_of(inc: dict, i: int) -> float:
    if not inc or i < inc["onset"] or i >= inc["end"]:
        return 0.0
    return min(1.0, (i - inc["onset"] + 1) / 4)


cell_kpm, slice_kpm, ue_kpm = [], [], []

# Cell KPM
for cell in cells:
    cid = cell["CellId"]
    base_prb = RNG.uniform(38, 62)
    inc = cell_incident.get(cid)
    for i in range(N_SAMPLES):
        prb = base_prb + RNG.uniform(-6, 6)
        rrc = RNG.uniform(98.5, 99.9)
        dl = RNG.uniform(180, 360)
        r = ramp_of(inc, i)
        if r > 0:
            k = inc["kind"]
            if k == "fronthaul":
                prb = 90 + r * 7 + RNG.uniform(-1.5, 1.5)
                rrc = 92 - r * 9 + RNG.uniform(-1.5, 1.5)
                dl = (180 + RNG.uniform(-20, 20)) * (1 - 0.55 * r)
            elif k == "midhaul":
                prb = 86 + r * 8 + RNG.uniform(-1.5, 1.5)
                rrc = 97 - r * 3 + RNG.uniform(-1.0, 1.0)
                dl = (200 + RNG.uniform(-20, 20)) * (1 - 0.45 * r)
            elif k == "pci":
                rrc = 90 - r * 5 + RNG.uniform(-1.5, 1.5)  # RRC only; PRB normal
            elif k == "backhaul":
                flap = (i % 2 == 0)
                dl = RNG.uniform(180, 360) * (1 - (0.7 if flap else 0.05) * r)
                rrc = (95 if flap else 99) - RNG.uniform(0, 1.5)
            elif k == "demand":
                prb = 91 + r * 5 + RNG.uniform(-1.5, 1.5)  # congested but RRC healthy
                rrc = RNG.uniform(98.0, 99.5)
                dl = (200 + RNG.uniform(-20, 20)) * (1 - 0.25 * r)
        cell_kpm.append({"CellId": cid, "Timestamp": ts(i),
                         "PRBUtilPct": round(prb, 1), "RRCSuccessPct": round(rrc, 2),
                         "DLThroughputMbps": round(dl, 1)})

# Slice KPM
for sid, sst, *_ in SLICES:
    sla = next(x for x in SLICES if x[0] == sid)
    base_lat = {"eMBB": 14, "URLLC": 3.2, "mMTC": 65}[sst]
    base_tput = sla[4] * RNG.uniform(1.2, 1.6)
    inc = slice_incident.get(sid)
    for i in range(N_SAMPLES):
        lat = base_lat * RNG.uniform(0.9, 1.1)
        tput = base_tput * RNG.uniform(0.9, 1.05)
        prb = RNG.uniform(40, 65)
        act = RNG.randint(40, 220)
        r = ramp_of(inc, i)
        if r > 0 and inc["kind"] == "fronthaul":
            lat = base_lat + r * 10 + RNG.uniform(-0.6, 0.6)  # 3.2 -> ~13ms (SLA 5ms)
            tput = sla[4] * (1 - 0.5 * r)
            prb = 90 + r * 6
            act = RNG.randint(60, 120)
        elif r > 0 and inc["kind"] == "mmtc":
            act = int(RNG.randint(800, 1400) * (1 + 2.5 * r))  # UE surge
            prb = 55 + r * 20
            lat = base_lat * RNG.uniform(0.95, 1.1)  # mMTC tolerant; no SLA breach
        slice_kpm.append({"SliceId": sid, "Timestamp": ts(i),
                          "LatencyMs": round(lat, 2), "ThroughputMbps": round(tput, 1),
                          "PRBUtilPct": round(prb, 1), "ActiveUEs": act})

# UE KPM
for ue in ues:
    uid = ue["UEId"]
    cid = ue["CellId"]
    base_cqi = RNG.uniform(9, 14)
    inc = cell_incident.get(cid)
    for i in range(N_SAMPLES):
        cqi = base_cqi + RNG.uniform(-1.5, 1.5)
        tput = RNG.uniform(20, 90)
        bler = RNG.uniform(0.5, 3.0)
        r = ramp_of(inc, i)
        if r > 0 and inc["kind"] in ("fronthaul", "midhaul"):
            cqi = max(2.0, base_cqi - r * (7 if inc["kind"] == "fronthaul" else 4))
            tput = RNG.uniform(20, 90) * (1 - (0.6 if inc["kind"] == "fronthaul" else 0.4) * r)
            bler = 3 + r * (12 if inc["kind"] == "fronthaul" else 6)
        elif r > 0 and inc["kind"] == "backhaul" and (i % 2 == 0):
            tput = RNG.uniform(20, 90) * (1 - 0.6 * r)
        ue_kpm.append({"UEId": uid, "Timestamp": ts(i), "CQI": round(cqi, 1),
                       "ThroughputMbps": round(tput, 1), "BLERPct": round(bler, 1)})

write_csv(TEL / "CellKPM.csv",
          ["CellId", "Timestamp", "PRBUtilPct", "RRCSuccessPct", "DLThroughputMbps"], cell_kpm)
write_csv(TEL / "SliceKPM.csv",
          ["SliceId", "Timestamp", "LatencyMs", "ThroughputMbps", "PRBUtilPct", "ActiveUEs"], slice_kpm)
write_csv(TEL / "UEKPM.csv",
          ["UEId", "Timestamp", "CQI", "ThroughputMbps", "BLERPct"], ue_kpm)

# ── Alarms ───────────────────────────────────────────────────────────────────
alarms = []
an = 0


def add_alarm(i, sev, src, atype, desc, slice_id=""):
    global an
    an += 1
    alarms.append({"AlarmId": f"ALM-{an:05d}", "Timestamp": ts(i), "Severity": sev,
                   "SourceNodeId": src, "AlarmType": atype, "Description": desc,
                   "SliceId": slice_id})


# Benign baseline: PTP clock drift within tolerance (the "do not over-alarm" guard).
for i in range(0, N_SAMPLES, 6):
    add_alarm(i, "MINOR", RNG.choice(gnbs)["gNBId"], "CLOCK_DRIFT",
              "PTP clock drift within tolerance (no KPI impact)")

for inc in INCIDENTS:
    k = inc["kind"]
    o, e = inc["onset"], inc["end"]
    tcells = sorted(inc["_cells"])
    if k == "fronthaul":
        for i in range(o, e):
            for cid in tcells:
                link = f"LINK-FH-{cid}"
                if i == o:
                    add_alarm(i, "CRITICAL", link, "FRONTHAUL_DEGRADED",
                              f"eCPRI fronthaul {link} optical power below threshold; CRC errors rising")
                add_alarm(i, "MAJOR", cid, "PRB_CONGESTION",
                          f"PRB utilisation on {cid} exceeded 90% sustained")
                if i in (o + 1, o + 2):
                    add_alarm(i, "MAJOR", cid, "RRC_SETUP_FAILURE",
                              f"RRC setup success on {cid} dropped below 95%")
            if i == o:
                add_alarm(i, "MAJOR", inc["du"], "DU_OVERLOAD",
                          f"{inc['du']} L1 load elevated following fronthaul degradation")
            if i == o + 1:
                add_alarm(i, "CRITICAL", inc["slice"], "SLA_BREACH",
                          "URLLC slice latency exceeded 5ms SLA (observed >10ms); penalty exposure active",
                          slice_id=inc["slice"])
    elif k == "pci":
        for cid in tcells:
            add_alarm(o, "MAJOR", cid, "PCI_COLLISION",
                      f"PCI mod-3 collision detected on {cid} after neighbour list change")
            for i in (o, o + 1, o + 2):
                add_alarm(i, "MAJOR", cid, "RRC_SETUP_FAILURE",
                          f"RRC setup success on {cid} dropped below 95% (no transport fault)")
    elif k == "midhaul":
        add_alarm(o, "MAJOR", inc["link"], "MIDHAUL_CONGESTION",
                  f"F1 midhaul {inc['link']} saturated; all served cells throughput-capped")
        for i in range(o, e, 2):
            for cid in tcells:
                add_alarm(i, "MINOR", cid, "PRB_CONGESTION",
                          f"PRB elevated on {cid} (uniform across DU — midhaul-bound)")
    elif k == "mmtc":
        add_alarm(o, "MAJOR", inc["slice"], "SIGNALING_STORM",
                  "mMTC mass-reattach storm: RRC attempt rate spiked; eMBB/URLLC slices protected",
                  slice_id=inc["slice"])
        add_alarm(o + 1, "MINOR", inc["gnb"], "RACH_OVERLOAD",
                  f"RACH preamble contention elevated on {inc['gnb']} (mMTC origin)")
    elif k == "backhaul":
        for i in range(o, e, 3):
            add_alarm(i, "MAJOR", inc["link"], "BACKHAUL_FLAP",
                      f"Backhaul N3 {inc['link']} flapping; intermittent gNB-wide throughput loss")
    elif k == "demand":
        for cid in tcells:
            for i in range(o, e, 3):
                add_alarm(i, "MAJOR", cid, "PRB_CONGESTION",
                          f"PRB on {cid} exceeded 90% (demand-driven; RRC healthy, no transport fault)")

write_csv(TEL / "AlarmStream.csv",
          ["AlarmId", "Timestamp", "Severity", "SourceNodeId", "AlarmType",
           "Description", "SliceId"], alarms)

# ── topology.json (frontend graph viz) ───────────────────────────────────────
nodes, edges = [], []


def node(nid, label, props, size):
    p = {k: str(v) for k, v in props.items()}
    p["_size"] = size
    nodes.append({"id": nid, "label": label, "properties": p})


node(core["CoreId"], "CoreNetwork", core, 12)
for x in gnbs:
    node(x["gNBId"], "gNB", x, 10)
for x in cus:
    node(x["CUId"], "CU", x, 8)
for x in dus:
    node(x["DUId"], "DU", x, 7)
for x in cells:
    node(x["CellId"], "Cell", x, 6)
for x in slices_rows:
    node(x["SliceId"], "Slice", x, 8)
for x in slapolicies:
    node(x["SLAPolicyId"], "SLAPolicy", x, 5)
for x in ues:
    node(x["UEId"], "UE", x, 4)
for x in links:
    node(x["LinkId"], "TransportLink", x, 5)

for cu in cus:
    edges.append({"source": cu["gNBId"], "target": cu["CUId"], "label": "hosts"})
for d in dus:
    edges.append({"source": d["gNBId"], "target": d["DUId"], "label": "hosts"})
    edges.append({"source": d["CUId"], "target": d["DUId"], "label": "controls"})
for c in cells:
    edges.append({"source": c["DUId"], "target": c["CellId"], "label": "serves"})
for cs in cell_slice:
    edges.append({"source": cs["CellId"], "target": cs["SliceId"], "label": "carries"})
for u in ues:
    edges.append({"source": u["UEId"], "target": u["CellId"], "label": "attached_to"})
    edges.append({"source": u["UEId"], "target": u["SliceId"], "label": "uses"})
for p in slapolicies:
    edges.append({"source": p["SliceId"], "target": p["SLAPolicyId"], "label": "governed_by"})
for ln in links:
    edges.append({"source": ln["LinkId"], "target": ln["SourceId"], "label": "link_source"})
    edges.append({"source": ln["LinkId"], "target": ln["TargetId"], "label": "link_target"})

(PACK / "topology.json").write_text(
    json.dumps({"topology_nodes": nodes, "topology_edges": edges}, indent=2), encoding="utf-8")
print(f"  topology.json: {len(nodes)} nodes, {len(edges)} edges")

print("\nSummary:")
print(f"  gNB={len(gnbs)} CU={len(cus)} DU={len(dus)} Cell={len(cells)} "
      f"Slice={len(slices_rows)} UE={len(ues)} Link={len(links)}")
print(f"  CellKPM={len(cell_kpm)} SliceKPM={len(slice_kpm)} UEKPM={len(ue_kpm)} Alarm={len(alarms)}")
for inc in INCIDENTS:
    print(f"  incident {inc['id']:22s} kind={inc['kind']:10s} cells={len(inc['_cells'])} "
          f"window={inc['onset']}-{inc['end']}")
print("GEN_DONE")
