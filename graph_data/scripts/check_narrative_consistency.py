#!/usr/bin/env python3
"""Narrative-consistency guardrail for the Sydney (telecom-playground-v2) demo.

The demo's credibility rests on the synthetic data actually backing every claim
in the story. This script re-derives the fibre-cut blast radius + SLA $ exposure
+ the shared-conduit ("fake redundancy") finding straight from the entity CSVs
and asserts they equal the narrative's claims. Run it after any data edit.

    python3 graph_data/scripts/check_narrative_consistency.py

Exit 0 = the synthetic narrative is internally true; nonzero = drift to fix.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "telecom-playground-v2"
ENT = PACK / "data" / "entities"

# The narrative's load-bearing claims (the script asserts the data still backs these).
FAULT_LINK = "LINK-SYD-MEL-FIBRE-01"
CLAIM_AFFECTED_VPNS = {"VPN-ACME-CORP", "VPN-BIGBANK"}
CLAIM_TOTAL_PENALTY = 75000
CLAIM_UNAFFECTED_VPN = "VPN-OZMINE"
CLAIM_SHARED_CONDUIT_BACKUP = "LINK-SYD-MEL-FIBRE-02"


def read(name: str) -> list[dict]:
    with (ENT / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    services = read("DimService.csv")
    sla = {r["ServiceId"]: r for r in read("DimSLAPolicy.csv")}
    deps = read("FactServiceDependency.csv")
    hops = read("FactMPLSPathHops.csv")
    conduit = read("FactConduitMapping.csv")

    # 1. Which MPLS paths traverse the fault link?
    down_paths = {h["PathId"] for h in hops if h["NodeId"] == FAULT_LINK}

    # 2. A service is "primary-affected" if its PRIMARY path is down.
    primary_path = {(d["ServiceId"]): d["DependsOnId"]
                    for d in deps if d.get("DependencyStrength") == "PRIMARY"}
    enterprise = {s["ServiceId"] for s in services if s["ServiceType"] == "EnterpriseVPN"}
    affected = {sid for sid in enterprise if primary_path.get(sid) in down_paths}

    # 3. SLA $ exposure summed over affected services.
    total = sum(int(sla[sid]["PenaltyPerHourUSD"]) for sid in affected if sid in sla)

    # 4. Shared-conduit ("fake redundancy") check.
    conduit_of = {c["LinkId"]: c["ConduitId"] for c in conduit}
    primary_conduit = conduit_of.get(FAULT_LINK)
    backup_conduit = conduit_of.get(CLAIM_SHARED_CONDUIT_BACKUP)
    shares_conduit = primary_conduit is not None and primary_conduit == backup_conduit

    checks = [
        ("affected VPNs == ACME + BigBank", affected == CLAIM_AFFECTED_VPNS, sorted(affected)),
        (f"total SLA exposure == ${CLAIM_TOTAL_PENALTY:,}/hr", total == CLAIM_TOTAL_PENALTY, f"${total:,}/hr"),
        (f"{CLAIM_UNAFFECTED_VPN} is NOT affected (bounded blast radius)",
         CLAIM_UNAFFECTED_VPN not in affected, primary_path.get(CLAIM_UNAFFECTED_VPN, "?")),
        ("backup fibre shares the primary's conduit (fake redundancy)",
         shares_conduit, f"{primary_conduit} vs {backup_conduit}"),
    ]

    print(f"Fault: {FAULT_LINK}  →  down MPLS paths: {sorted(down_paths)}\n")
    ok = True
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}  ({detail})")
        ok = ok and passed

    print()
    if ok:
        print("NARRATIVE_CONSISTENT — the Sydney demo's data backs every claim "
              f"(blast radius {sorted(affected)}, ${total:,}/hr, shared conduit "
              f"{primary_conduit}).")
        return 0
    print("NARRATIVE_DRIFT — the data no longer matches the story. Fix before demo.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
