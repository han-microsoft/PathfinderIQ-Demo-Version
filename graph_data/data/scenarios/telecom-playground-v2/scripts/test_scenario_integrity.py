#!/usr/bin/env python3
"""Scenario integrity tests — validates data supports expected agent reasoning chains.

Run from the scenario root:
    cd telecom-playground-v2
    python3 -m pytest scripts/test_scenario_integrity.py -v

Dependencies: pandas, networkx, pyyaml (all in backend venv).
No LLM, no Azure, no network calls. ~1 second total.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

# ── Paths ────────────────────────────────────────────────────────────────────

SCENARIO_ROOT = Path(__file__).resolve().parent.parent
ENTITY_DIR = SCENARIO_ROOT / "data" / "entities"
TELEMETRY_DIR = SCENARIO_ROOT / "data" / "telemetry"
KNOWLEDGE_DIR = SCENARIO_ROOT / "data" / "knowledge"
PROMPTS_DIR = SCENARIO_ROOT / "data" / "prompts"

INCIDENT_TIME = datetime(2026, 2, 6, 14, 31, 14, tzinfo=timezone.utc)
INCIDENT_TS_PREFIX = "2026-02-06T14:31:14"


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_csv(path: Path) -> list[dict]:
    """Load a CSV file as a list of dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_topology() -> dict:
    """Load topology.json."""
    with open(SCENARIO_ROOT / "topology.json", encoding="utf-8") as f:
        return json.load(f)


def load_scenario_yaml() -> dict:
    """Load scenario.yaml."""
    with open(SCENARIO_ROOT / "scenario.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_graph():
    """Build a NetworkX graph from topology.json for traversal tests."""
    import networkx as nx
    topo = load_topology()
    g = nx.MultiDiGraph()
    for node in topo["topology_nodes"]:
        g.add_node(node["id"], label=node["label"], **node.get("properties", {}))
    for edge in topo["topology_edges"]:
        g.add_edge(edge["source"], edge["target"], label=edge["label"],
                   **edge.get("properties", {}))
    return g


# ═══════════════════════════════════════════════════════════════════════════
# 11.1 — Graph Traversal Integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestGraphTraversal:
    """Verify the topology graph supports the expected agent reasoning paths."""

    @pytest.fixture(scope="class")
    def graph(self):
        return build_graph()

    @pytest.fixture(scope="class")
    def topo(self):
        return load_topology()

    def test_node_count(self, topo):
        """90 nodes after vibration sensor removal."""
        assert len(topo["topology_nodes"]) == 90

    def test_edge_count(self, topo):
        """~111 edges after vibration sensor edge removal."""
        assert len(topo["topology_edges"]) == 111

    def test_vpn_acme_exists(self, graph):
        """VPN-ACME-CORP node exists in topology."""
        assert "VPN-ACME-CORP" in graph.nodes

    def test_fibre01_exists(self, graph):
        """LINK-SYD-MEL-FIBRE-01 node exists in topology."""
        assert "LINK-SYD-MEL-FIBRE-01" in graph.nodes

    def test_fibre01_has_three_optical_sensors(self, graph):
        """LINK-SYD-MEL-FIBRE-01 has exactly 3 OpticalPower sensors monitoring it."""
        sensors = [
            n for n in graph.predecessors("LINK-SYD-MEL-FIBRE-01")
            if graph.nodes[n].get("label") == "Sensor"
            and graph.nodes[n].get("SensorType") == "OpticalPower"
        ]
        assert len(sensors) == 3
        sensor_ids = {s for s in sensors}
        assert sensor_ids == {
            "SENS-SYD-MEL-F1-OPT-001",
            "SENS-SYD-MEL-F1-OPT-002",
            "SENS-SYD-MEL-F1-OPT-003",
        }

    def test_shared_risk_conduit(self, graph):
        """FIBRE-01 and FIBRE-02 share at least one conduit."""
        conduits_01 = {
            t for _, t, d in graph.edges("LINK-SYD-MEL-FIBRE-01", data=True)
            if d.get("label") == "routed_through"
        }
        conduits_02 = {
            t for _, t, d in graph.edges("LINK-SYD-MEL-FIBRE-02", data=True)
            if d.get("label") == "routed_through"
        }
        assert conduits_01 & conduits_02, "FIBRE-01 and FIBRE-02 share no conduit"

    def test_sla_policies_exist(self, graph):
        """VPN-ACME-CORP and VPN-BIGBANK each have an SLA policy node connected."""
        sla_nodes = [
            n for n in graph.nodes
            if graph.nodes[n].get("label") == "SLAPolicy"
        ]
        sla_service_ids = {graph.nodes[n].get("ServiceId") for n in sla_nodes}
        assert "VPN-ACME-CORP" in sla_service_ids
        assert "VPN-BIGBANK" in sla_service_ids


# ═══════════════════════════════════════════════════════════════════════════
# 11.2 — Telemetry Forensic Signature
# ═══════════════════════════════════════════════════════════════════════════


class TestTelemetrySignature:
    """Verify generated telemetry CSVs contain the correct incident pattern."""

    @pytest.fixture(scope="class")
    def sensor_readings(self):
        return load_csv(TELEMETRY_DIR / "SensorReadings.csv")

    @pytest.fixture(scope="class")
    def link_telemetry(self):
        return load_csv(TELEMETRY_DIR / "LinkTelemetry.csv")

    @pytest.fixture(scope="class")
    def alerts(self):
        return load_csv(TELEMETRY_DIR / "AlertStream.csv")

    def test_sensor_opt002_cliff(self, sensor_readings):
        """OPT-002 (Goulburn) shows loss-of-light (< -30 dBm) after incident."""
        post = [
            r for r in sensor_readings
            if r["SensorId"] == "SENS-SYD-MEL-F1-OPT-002"
            and r["Timestamp"] >= "2026-02-06T14:31:14"
        ]
        assert len(post) > 0
        for r in post:
            assert float(r["Value"]) < -30, f"OPT-002 should be < -30 dBm, got {r['Value']}"

    def test_sensor_opt001_stable(self, sensor_readings):
        """OPT-001 (Campbelltown) stays in normal range throughout."""
        all_opt001 = [
            r for r in sensor_readings
            if r["SensorId"] == "SENS-SYD-MEL-F1-OPT-001"
        ]
        for r in all_opt001:
            val = float(r["Value"])
            assert val > -15, f"OPT-001 should stay normal, got {val}"

    def test_alert_storm_20_in_1_second(self, alerts):
        """Exactly 20 SERVICE_DEGRADATION alerts between 14:31:14.000 and 14:31:14.999."""
        storm = [
            a for a in alerts
            if a["Timestamp"].startswith("2026-02-06T14:31:14")
            and a["AlertType"] == "SERVICE_DEGRADATION"
        ]
        assert len(storm) == 20

    def test_fibre01_link_down(self, link_telemetry):
        """LINK-SYD-MEL-FIBRE-01 shows Utilization 0% after incident."""
        post = [
            r for r in link_telemetry
            if r["LinkId"] == "LINK-SYD-MEL-FIBRE-01"
            and r["Timestamp"] >= "2026-02-06T14:31:14"
        ]
        assert len(post) > 0
        for r in post:
            assert float(r["UtilizationPct"]) == 0.0

    def test_no_vibration_sensor_data(self, sensor_readings):
        """No SensorType == 'Vibration' in SensorReadings."""
        types = {r["SensorType"] for r in sensor_readings}
        assert "Vibration" not in types

    def test_background_noise_exists(self, alerts):
        """Pre-incident window has background noise alerts."""
        pre = [
            a for a in alerts
            if a["Timestamp"] < "2026-02-06T14:31:14"
        ]
        assert len(pre) > 3000, f"Expected > 3000 noise alerts, got {len(pre)}"


# ═══════════════════════════════════════════════════════════════════════════
# 11.3 — Knowledge Document Integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestKnowledgeDocs:
    """Verify knowledge documents are correct and complete."""

    def test_fibre_cut_runbook_has_sensor_localisation(self):
        """fibre_cut_runbook.md contains the per-sensor fault localisation section."""
        text = (KNOWLEDGE_DIR / "runbooks" / "fibre_cut_runbook.md").read_text()
        assert "Per-Sensor Fault Localisation" in text
        assert "Diagnostic Logic" in text
        assert "Shared-Risk Conduit Check" in text

    def test_precedent_ticket_has_telemetry(self):
        """INC-2025-11-22-0055 contains telemetry signature data."""
        text = (KNOWLEDGE_DIR / "tickets" / "INC-2025-11-22-0055.txt").read_text()
        assert "Telemetry Signature" in text or "OPT-002" in text or "SENS-SYD-MEL" in text

    def test_runbook_count(self):
        """15 total runbooks."""
        runbooks = list(KNOWLEDGE_DIR.joinpath("runbooks").glob("*.md"))
        assert len(runbooks) == 15, f"Expected 15, got {len(runbooks)}: {[r.name for r in runbooks]}"

    def test_ticket_count(self):
        """20 total tickets."""
        tickets = list(KNOWLEDGE_DIR.joinpath("tickets").glob("*.txt"))
        assert len(tickets) == 20, f"Expected 20, got {len(tickets)}"

    def test_no_wear_tear_references(self):
        """No file contains 'wear and tear' or 'gradual degradation'."""
        violations = []
        for f in SCENARIO_ROOT.rglob("*"):
            if f.is_file() and f.suffix in (".md", ".txt", ".yaml", ".csv", ".json"):
                if "IMPLEMENTATION_PLAN" in f.name:
                    continue  # The plan itself references these terms
                text = f.read_text(errors="ignore").lower()
                if "wear and tear" in text:
                    violations.append(f"{f}: contains 'wear and tear'")
                if "gradual degradation" in text:
                    violations.append(f"{f}: contains 'gradual degradation'")
        assert not violations, "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════════
# 11.4 — Dispatch Chain Integrity
# ═══════════════════════════════════════════════════════════════════════════


class TestDispatchChain:
    """Verify the data supports the dispatch workflow."""

    @pytest.fixture(scope="class")
    def roster(self):
        return load_csv(ENTITY_DIR / "DimDutyRoster.csv")

    @pytest.fixture(scope="class")
    def depots(self):
        return load_csv(ENTITY_DIR / "DimDepot.csv")

    @pytest.fixture(scope="class")
    def sensors(self):
        return load_csv(ENTITY_DIR / "DimSensor.csv")

    def test_goulburn_engineer_on_duty(self, roster):
        """A RegionalFieldEngineer at Goulburn is in the roster."""
        goulburn_engineers = [
            r for r in roster
            if r["City"] == "Goulburn" and r["Role"] == "RegionalFieldEngineer"
        ]
        assert len(goulburn_engineers) >= 1

    def test_goulburn_depot_services_amplifier(self, depots):
        """DEPOT-GOULBURN services AMP-SYD-MEL-GOULBURN."""
        goulburn = [d for d in depots if d["DepotId"] == "DEPOT-GOULBURN"]
        assert len(goulburn) == 1
        assert goulburn[0]["ServicedEntityId"] == "AMP-SYD-MEL-GOULBURN"

    def test_sensor_opt002_gps(self, sensors):
        """SENS-SYD-MEL-F1-OPT-002 GPS is near Goulburn (-34.7546, 149.7186)."""
        s = [s for s in sensors if s["SensorId"] == "SENS-SYD-MEL-F1-OPT-002"]
        assert len(s) == 1
        assert abs(float(s[0]["Latitude"]) - (-34.7546)) < 0.01
        assert abs(float(s[0]["Longitude"]) - 149.7186) < 0.01

    def test_depot_equipment_docs_exist(self):
        """Campbelltown depot equipment manifest exists and mentions OTDR."""
        manifest = KNOWLEDGE_DIR / "equipment" / "DEPOT-SYD-CAMPBELLTOWN-manifest.md"
        assert manifest.exists()
        text = manifest.read_text()
        assert "OTDR" in text or "T-BERD" in text


# ═══════════════════════════════════════════════════════════════════════════
# 11.5 — Scenario Config
# ═══════════════════════════════════════════════════════════════════════════


class TestScenarioConfig:
    """Verify scenario.yaml is coherent."""

    @pytest.fixture(scope="class")
    def cfg(self):
        return load_scenario_yaml()

    def test_scenario_name(self, cfg):
        assert cfg["name"] == "telecom-playground-v2"

    def test_agent_count(self, cfg):
        """4 agent definitions."""
        agent_keys = [
            k for k in cfg["agents"]
            if k not in ("default", "mode") and isinstance(cfg["agents"][k], dict)
        ]
        assert len(agent_keys) == 4

    def test_default_agent(self, cfg):
        assert cfg["agents"]["default"] == "orchestrator"

    def test_all_prompt_files_exist(self, cfg):
        """Every prompt file referenced in agent instructions exists."""
        missing = []
        for agent_id, agent_cfg in cfg["agents"].items():
            if agent_id in ("default", "mode") or not isinstance(agent_cfg, dict):
                continue
            for path in agent_cfg.get("instructions", []):
                if path.startswith("{"):
                    continue
                full = PROMPTS_DIR / path
                if not full.exists():
                    missing.append(str(full))
        assert not missing, f"Missing prompt files: {missing}"

    def test_single_demo_flow(self, cfg):
        """Exactly 1 demo flow with 4 steps."""
        assert len(cfg["demo_flows"]) == 1
        assert len(cfg["demo_flows"][0]["steps"]) == 4

    def test_no_vibration_in_baselines(self, cfg):
        """telemetry_baselines.sensor_readings has no Vibration metric."""
        metrics = [b["metric"] for b in cfg["telemetry_baselines"]["sensor_readings"]]
        assert not any("vibration" in m.lower() for m in metrics)


# ═══════════════════════════════════════════════════════════════════════════
# 11.6 — Anti-Cargo-Culting
# ═══════════════════════════════════════════════════════════════════════════


class TestAntiCargoCulting:
    """Verify prompts don't leak forensic answers."""

    def test_no_forensic_sensor_in_query_examples(self):
        """OPT-002 (the forensic key) should not appear in KQL query examples."""
        for f in PROMPTS_DIR.rglob("*.md"):
            if "fibre_cut_runbook" in f.name or "graph_schema" in f.name:
                continue
            text = f.read_text()
            lines = text.split("\n")
            for line in lines:
                if "SENS-SYD-MEL-F1-OPT-002" in line and ("where" in line.lower() or "|" in line):
                    pytest.fail(f"{f.name}: contains OPT-002 in a query example: {line.strip()}")
