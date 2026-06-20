"""Swap-proof regression — telecom-playground-v2 <-> demo-sandbox.

Proves a clean runtime use-case swap over a constant backend core:
  - the catalog lists both packs;
  - the X-Scenario-Name header rebinds scenario metadata, agents, and topology;
  - the demo-sandbox's cloud-free tool returns its bundled static dataset;
  - swapping back and forth is stable (no cross-scenario bleed).
"""

TELECOM = "telecom-playground-v2"
SANDBOX = "demo-sandbox"


class TestScenarioSwapProof:
    def test_catalog_lists_both_packs(self, client):
        names = {s["name"] for s in client.get("/api/scenarios").json()["scenarios"]}
        assert {TELECOM, SANDBOX} <= names

    def test_header_rebinds_scenario_metadata(self, client):
        tele = client.get("/api/scenario", headers={"X-Scenario-Name": TELECOM}).json()
        sand = client.get("/api/scenario", headers={"X-Scenario-Name": SANDBOX}).json()
        assert tele["scenario_name"] == TELECOM
        assert sand["scenario_name"] == SANDBOX
        assert sand["domain"] == "sandbox"
        assert tele["display_name"] != sand["display_name"]

    def test_header_rebinds_agents(self, client):
        def agent_names(scenario: str) -> set[str]:
            resp = client.get("/api/agents/", headers={"X-Scenario-Name": scenario})
            assert resp.status_code == 200
            return {a.get("name") or a.get("id") for a in resp.json()}

        tele_agents = agent_names(TELECOM)
        sand_agents = agent_names(SANDBOX)
        assert "NetworkInvestigator" in tele_agents
        assert "SandboxGuide" in sand_agents
        assert tele_agents.isdisjoint(sand_agents)

    def test_header_rebinds_topology(self, client):
        def labels(scenario: str) -> set[str]:
            resp = client.get("/api/scenario/topology", headers={"X-Scenario-Name": scenario})
            nodes = resp.json().get("topology_nodes", [])
            return {n.get("label") for n in nodes}

        assert "CoreRouter" in labels(TELECOM)
        assert "SandboxNode" in labels(SANDBOX)

    def test_swap_back_and_forth_is_stable(self, client):
        seq = [TELECOM, SANDBOX, TELECOM, SANDBOX]
        for s in seq:
            assert client.get("/api/scenarios", headers={"X-Scenario-Name": s}).json()["active"] == s


class TestSandboxToolStaticData:
    def test_sandbox_tools_read_bundled_dataset(self):
        from app.foundation.request_scope import build_request_scope, set_request_scope, reset_request_scope
        import tools.sandbox as sandbox

        token = set_request_scope(build_request_scope(scenario_name=SANDBOX))
        try:
            status = sandbox.sandbox_status.func() if hasattr(sandbox.sandbox_status, "func") else sandbox.sandbox_status()
            items = sandbox.sandbox_list_items.func() if hasattr(sandbox.sandbox_list_items, "func") else sandbox.sandbox_list_items()
        finally:
            reset_request_scope(token)

        assert status["item_count"] == 4
        assert status["dataset"] == "demo-sandbox-dataset"
        assert items["row_count"] == 4
        assert "SBX-001" in {r[0] for r in items["rows"]}


class TestPerScenarioCosmosBinding:
    """P2: Cosmos db/container names resolve from the active scenario's manifest."""

    def test_graph_binding_rebinds_per_scenario(self):
        from app.foundation.request_scope import build_request_scope, set_request_scope, reset_request_scope
        from app.foundation.config import settings
        import tools._cosmos as cosmos

        # demo-sandbox declares data_sources.graph.database: sandbox
        token = set_request_scope(build_request_scope(scenario_name=SANDBOX))
        try:
            assert cosmos._resolve_gremlin_target().database == "sandbox"
        finally:
            reset_request_scope(token)

        # telecom has no data_sources.graph block -> falls back to settings default
        token = set_request_scope(build_request_scope(scenario_name=TELECOM))
        try:
            assert cosmos._resolve_gremlin_target().database == settings.cosmos_gremlin_database
        finally:
            reset_request_scope(token)
