#!/usr/bin/env python3
"""Seed Cosmos DB (Gremlin graph + NoSQL telemetry) from scenario CSVs.

Replaces the Fabric deploy pipeline (deploy_graph.py / deploy_telemetry.py) for
the Cosmos-backed deployment. Reads the telecom scenario CSVs and loads:

    GRAPH (Cosmos Gremlin)  — one vertex per Dim* row (label = entity type),
                              edges from Fact* mappings + foreign-key columns.
    TELEMETRY (Cosmos NoSQL)— AlertStream → 'alerts' container; LinkTelemetry +
                              SensorReadings → 'telemetry' container (merged,
                              discriminated by a 'kind' field).

Auth: DefaultAzureCredential / AzureCliCredential (data-plane RBAC, no keys).

Usage:
    python3 graph_data/scripts/seed_cosmos.py \
        --gremlin-endpoint wss://<acct>.gremlin.cosmos.azure.com:443/ \
        --nosql-endpoint   https://<acct>.documents.azure.com:443/ \
        --scenario-dir graph_data/data/scenarios/telecom-playground-v2 \
        [--graph-only | --telemetry-only] [--wipe]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from azure.identity import AzureCliCredential, DefaultAzureCredential

# ── Graph schema: vertex files → label + id column ───────────────────────────
# (CSV filename stem, vertex label, id column, partition-key value)
VERTEX_SPECS = [
    ("DimCoreRouter", "CoreRouter", "RouterId"),
    ("DimAggSwitch", "AggSwitch", "SwitchId"),
    ("DimBaseStation", "BaseStation", "StationId"),
    ("DimTransportLink", "TransportLink", "LinkId"),
    ("DimService", "Service", "ServiceId"),
    ("DimSensor", "Sensor", "SensorId"),
    ("DimMPLSPath", "MPLSPath", "PathId"),
    ("DimPhysicalConduit", "PhysicalConduit", "ConduitId"),
    ("DimAmplifierSite", "AmplifierSite", "SiteId"),
    ("DimBGPSession", "BGPSession", "SessionId"),
    ("DimSLAPolicy", "SLAPolicy", "SLAPolicyId"),
    ("DimAdvisory", "Advisory", "AdvisoryId"),
    ("DimDepot", "Depot", "DepotId"),
    ("DimDutyRoster", "DutyRoster", "RosterId"),
]

# Edges derived from foreign-key columns on Dim rows:
# (CSV stem, source-id column, target-id column, edge label)
FK_EDGE_SPECS = [
    ("DimTransportLink", "LinkId", "SourceRouterId", "connects_source"),
    ("DimTransportLink", "LinkId", "TargetRouterId", "connects_target"),
    ("DimAggSwitch", "SwitchId", "UplinkRouterId", "uplinks_to"),
    ("DimBaseStation", "StationId", "AggSwitchId", "backhauls_via"),
    ("DimSensor", "SensorId", "MonitoredEntityId", "monitors"),
    ("DimBGPSession", "SessionId", "PeerARouterId", "peers"),
    ("DimBGPSession", "SessionId", "PeerBRouterId", "peers"),
    ("DimSLAPolicy", "SLAPolicyId", "ServiceId", "governs"),
    ("DimDepot", "DepotId", "ServicedEntityId", "services"),
    ("DimDutyRoster", "RosterId", "DepotId", "stationed_at"),
]

# Edges derived from Fact* mapping tables:
# (CSV stem, source-id column, target-id column, edge label)
FACT_EDGE_SPECS = [
    ("FactServiceDependency", "ServiceId", "DependsOnId", "depends_on"),
    ("FactMPLSPathHops", "PathId", "NodeId", "traverses"),
    ("FactAmplifierMapping", "SiteId", "LinkId", "amplifies"),
    ("FactConduitMapping", "LinkId", "ConduitId", "routed_through"),
    ("FactAdvisoryMapping", "AdvisoryId", "RouterId", "affects"),
]

_PK = "pfiq"  # constant partition-key value for all vertices


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _gesc(val: str) -> str:
    """Escape a string for inline Gremlin string literals."""
    return val.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def _credential():
    try:
        cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        cred.get_token("https://cosmos.azure.com/.default")
        return cred
    except Exception:
        return AzureCliCredential()


# ── Graph seeding (Cosmos Gremlin) ───────────────────────────────────────────


def seed_graph(endpoint: str, database: str, graph: str, entities_dir: Path, wipe: bool) -> None:
    from gremlin_python.driver import client as gremlin_client, serializer

    cred = _credential()
    token = cred.get_token("https://cosmos.azure.com/.default").token
    gc = gremlin_client.Client(
        url=endpoint,
        traversal_source="g",
        username=f"/dbs/{database}/colls/{graph}",
        password=token,
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )

    def submit(q: str) -> None:
        for attempt in range(5):
            try:
                gc.submit(q).all().result()
                return
            except Exception as exc:
                msg = str(exc).lower()
                if "429" in msg or "request rate" in msg or "throttl" in msg:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"Gremlin submit failed after retries: {q[:120]}")

    if wipe:
        print("  wiping graph ...")
        submit("g.V().drop()")

    # Vertices
    vcount = 0
    valid_ids: set[str] = set()
    for stem, label, id_col in VERTEX_SPECS:
        rows = _read_csv(entities_dir / f"{stem}.csv")
        for row in rows:
            vid = (row.get(id_col) or "").strip()
            if not vid:
                continue
            valid_ids.add(vid)
            props = "".join(
                f".property('{_gesc(k)}', '{_gesc(str(v))}')"
                for k, v in row.items()
                if v not in (None, "")
            )
            q = (
                f"g.V('{_gesc(vid)}').fold().coalesce(unfold(), "
                f"addV('{label}').property('id', '{_gesc(vid)}')"
                f".property('pk', '{_PK}'){props})"
            )
            submit(q)
            vcount += 1
    print(f"  vertices: {vcount}")

    # Edges (FK + Fact). Skip edges whose endpoints were not loaded as vertices.
    ecount = 0
    for specs in (FK_EDGE_SPECS, FACT_EDGE_SPECS):
        for stem, src_col, tgt_col, elabel in specs:
            for row in _read_csv(entities_dir / f"{stem}.csv"):
                src = (row.get(src_col) or "").strip()
                tgt = (row.get(tgt_col) or "").strip()
                if not src or not tgt or src not in valid_ids or tgt not in valid_ids:
                    continue
                q = (
                    f"g.V('{_gesc(src)}').as('a').V('{_gesc(tgt)}')"
                    f".coalesce(__.inE('{elabel}').where(outV().as('a')), "
                    f"__.addE('{elabel}').from('a'))"
                )
                submit(q)
                ecount += 1
    print(f"  edges: {ecount}")
    gc.close()


# ── Telemetry seeding (Cosmos NoSQL) ─────────────────────────────────────────


def seed_telemetry(endpoint: str, database: str, telem_dir: Path, wipe: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from azure.cosmos import CosmosClient

    cred = _credential()
    client = CosmosClient(endpoint, credential=cred)
    db = client.get_database_client(database)

    alerts = db.get_container_client("alerts")
    telem = db.get_container_client("telemetry")

    def _bulk_upsert(container, docs: list[dict], label: str) -> None:
        done = 0
        total = len(docs)

        def _put(doc):
            container.upsert_item(doc)

        with ThreadPoolExecutor(max_workers=32) as pool:
            for _ in pool.map(_put, docs):
                done += 1
                if done % 2000 == 0:
                    print(f"  {label}: {done}/{total}", flush=True)
        print(f"  {label}: {total}", flush=True)

    # AlertStream → alerts (id = AlertId, pk = SourceNodeId)
    alert_docs = []
    for row in _read_csv(telem_dir / "AlertStream.csv"):
        doc = dict(row)
        doc["id"] = row["AlertId"]
        alert_docs.append(doc)
    _bulk_upsert(alerts, alert_docs, "alerts")

    # LinkTelemetry + SensorReadings → telemetry (id, pk = entityId, kind discriminator)
    telem_docs = []
    for row in _read_csv(telem_dir / "LinkTelemetry.csv"):
        doc = dict(row)
        doc["kind"] = "link"
        doc["entityId"] = row["LinkId"]
        doc["id"] = f"link-{row['LinkId']}-{row['Timestamp']}"
        telem_docs.append(doc)
    for row in _read_csv(telem_dir / "SensorReadings.csv"):
        doc = dict(row)
        doc["kind"] = "sensor"
        doc["entityId"] = row["SensorId"]
        doc["id"] = row.get("ReadingId") or f"sensor-{row['SensorId']}-{row['Timestamp']}"
        telem_docs.append(doc)
    _bulk_upsert(telem, telem_docs, "telemetry")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gremlin-endpoint", default="")
    ap.add_argument("--nosql-endpoint", default="")
    ap.add_argument("--gremlin-database", default="pfiq")
    ap.add_argument("--gremlin-graph", default="topology")
    ap.add_argument("--nosql-database", default="pfiq")
    ap.add_argument("--scenario-dir", required=True)
    ap.add_argument("--graph-only", action="store_true")
    ap.add_argument("--telemetry-only", action="store_true")
    ap.add_argument("--wipe", action="store_true")
    args = ap.parse_args()

    data_dir = Path(args.scenario_dir) / "data"
    entities_dir = data_dir / "entities"
    telem_dir = data_dir / "telemetry"

    if not args.telemetry_only:
        if not args.gremlin_endpoint:
            print("ERROR: --gremlin-endpoint required for graph seeding", file=sys.stderr)
            return 2
        print(f"Seeding GRAPH → {args.gremlin_endpoint}")
        seed_graph(args.gremlin_endpoint, args.gremlin_database, args.gremlin_graph, entities_dir, args.wipe)

    if not args.graph_only:
        if not args.nosql_endpoint:
            print("ERROR: --nosql-endpoint required for telemetry seeding", file=sys.stderr)
            return 2
        print(f"Seeding TELEMETRY → {args.nosql_endpoint}")
        seed_telemetry(args.nosql_endpoint, args.nosql_database, telem_dir, args.wipe)

    print("SEED_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
