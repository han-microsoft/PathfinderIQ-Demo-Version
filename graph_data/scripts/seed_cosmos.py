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


# ── Schema-driven seeding (generic, any scenario) ────────────────────────────
# Reads the pack's own declarations so new datasets drop in without editing this
# file: graph from graph_schema.yaml (vertices + edges), telemetry from
# telemetry_schema.yaml (CSV → container mapping). Opt in with --schema-driven.


def _load_yaml(path: Path) -> dict:
    import yaml
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def seed_graph_schema_driven(
    endpoint: str, database: str, graph: str, scenario_dir: Path, entities_dir: Path, wipe: bool,
) -> None:
    """Seed the Gremlin graph from the pack's graph_schema.yaml.

    Vertex spec: {label, csv_file, id_column, properties: [col, ...]}.
    Edge spec:   {label, csv_file, source: {column}, target: {column},
                  properties: [{name, value}]}  (edge props are constants).
    All vertices get a constant ``pk`` so the container's partition key resolves.
    """
    from gremlin_python.driver import client as gremlin_client, serializer

    schema = _load_yaml(scenario_dir / "graph_schema.yaml")
    vertices = schema.get("vertices", []) or []
    edges = schema.get("edges", []) or []

    cred = _credential()
    token = cred.get_token("https://cosmos.azure.com/.default").token
    gc = gremlin_client.Client(
        url=endpoint, traversal_source="g",
        username=f"/dbs/{database}/colls/{graph}", password=token,
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

    valid_ids: set[str] = set()
    vcount = 0
    for vspec in vertices:
        label = vspec["label"]
        id_col = vspec["id_column"]
        prop_cols = vspec.get("properties", []) or []
        for row in _read_csv(entities_dir / vspec["csv_file"]):
            vid = (row.get(id_col) or "").strip()
            if not vid:
                continue
            valid_ids.add(vid)
            cols = prop_cols or list(row.keys())
            props = "".join(
                f".property('{_gesc(c)}', '{_gesc(str(row[c]))}')"
                for c in cols
                if c in row and row[c] not in (None, "")
            )
            q = (
                f"g.V('{_gesc(vid)}').fold().coalesce(unfold(), "
                f"addV('{_gesc(label)}').property('id', '{_gesc(vid)}')"
                f".property('pk', '{_PK}'){props})"
            )
            submit(q)
            vcount += 1
    print(f"  vertices: {vcount}")

    ecount = 0
    for espec in edges:
        elabel = espec["label"]
        src_col = espec["source"]["column"]
        tgt_col = espec["target"]["column"]
        eprops = "".join(
            f".property('{_gesc(str(p['name']))}', '{_gesc(str(p['value']))}')"
            for p in (espec.get("properties", []) or [])
            if isinstance(p, dict) and "name" in p and "value" in p
        )
        for row in _read_csv(entities_dir / espec["csv_file"]):
            src = (row.get(src_col) or "").strip()
            tgt = (row.get(tgt_col) or "").strip()
            if not src or not tgt or src not in valid_ids or tgt not in valid_ids:
                continue
            q = (
                f"g.V('{_gesc(src)}').as('a').V('{_gesc(tgt)}')"
                f".coalesce(__.inE('{_gesc(elabel)}').where(outV().as('a')), "
                f"__.addE('{_gesc(elabel)}').from('a'){eprops})"
            )
            submit(q)
            ecount += 1
    print(f"  edges: {ecount}")
    gc.close()


def seed_telemetry_schema_driven(
    endpoint: str, database: str, scenario_dir: Path, telem_dir: Path, wipe: bool,
) -> None:
    """Seed Cosmos NoSQL telemetry/alerts from the pack's telemetry_schema.yaml.

    Source spec: {container, csv_file, id_column | id_template,
                  entity_column (-> entityId), kind}.
    """
    from concurrent.futures import ThreadPoolExecutor
    from azure.cosmos import CosmosClient

    manifest = _load_yaml(scenario_dir / "telemetry_schema.yaml")
    sources = manifest.get("sources", []) or []

    cred = _credential()
    client = CosmosClient(endpoint, credential=cred)
    db = client.get_database_client(database)

    by_container: dict[str, list[dict]] = {}
    for spec in sources:
        container_name = spec["container"]
        id_col = spec.get("id_column")
        id_tmpl = spec.get("id_template")
        entity_col = spec.get("entity_column")
        kind = spec.get("kind")
        for row in _read_csv(telem_dir / spec["csv_file"]):
            doc = dict(row)
            if id_col and row.get(id_col):
                doc["id"] = row[id_col]
            elif id_tmpl:
                try:
                    doc["id"] = id_tmpl.format(**row)
                except (KeyError, IndexError):
                    doc["id"] = f"{container_name}-{len(by_container.get(container_name, []))}"
            if entity_col and row.get(entity_col):
                doc["entityId"] = row[entity_col]
            if kind:
                doc["kind"] = kind
            by_container.setdefault(container_name, []).append(doc)

    for container_name, docs in by_container.items():
        container = db.get_container_client(container_name)
        total = len(docs)
        done = 0

        def _upsert(d: dict) -> None:
            from azure.cosmos.exceptions import CosmosHttpResponseError
            for attempt in range(6):
                try:
                    container.upsert_item(d)
                    return
                except CosmosHttpResponseError as exc:
                    if exc.status_code == 429:
                        wait = getattr(exc, "retry_after", None) or (0.5 * (attempt + 1))
                        time.sleep(float(wait) if wait else 0.5)
                        continue
                    raise
            raise RuntimeError(f"upsert failed after retries: {d.get('id')}")

        with ThreadPoolExecutor(max_workers=16) as pool:
            for _ in pool.map(_upsert, docs):
                done += 1
                if done % 2000 == 0:
                    print(f"  {container_name}: {done}/{total}", flush=True)
        print(f"  {container_name}: {total}", flush=True)


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
    ap.add_argument(
        "--schema-driven", action="store_true",
        help="Seed generically from the pack's graph_schema.yaml + telemetry_schema.yaml "
             "(for any scenario). Default = the legacy telecom-hardcoded path.",
    )
    args = ap.parse_args()

    scenario_dir = Path(args.scenario_dir)
    data_dir = scenario_dir / "data"
    entities_dir = data_dir / "entities"
    telem_dir = data_dir / "telemetry"

    if not args.telemetry_only:
        if not args.gremlin_endpoint:
            print("ERROR: --gremlin-endpoint required for graph seeding", file=sys.stderr)
            return 2
        print(f"Seeding GRAPH → {args.gremlin_endpoint}")
        if args.schema_driven:
            seed_graph_schema_driven(
                args.gremlin_endpoint, args.gremlin_database, args.gremlin_graph,
                scenario_dir, entities_dir, args.wipe,
            )
        else:
            seed_graph(args.gremlin_endpoint, args.gremlin_database, args.gremlin_graph, entities_dir, args.wipe)

    if not args.graph_only:
        if not args.nosql_endpoint:
            print("ERROR: --nosql-endpoint required for telemetry seeding", file=sys.stderr)
            return 2
        print(f"Seeding TELEMETRY → {args.nosql_endpoint}")
        if args.schema_driven:
            seed_telemetry_schema_driven(args.nosql_endpoint, args.nosql_database, scenario_dir, telem_dir, args.wipe)
        else:
            seed_telemetry(args.nosql_endpoint, args.nosql_database, telem_dir, args.wipe)

    print("SEED_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
