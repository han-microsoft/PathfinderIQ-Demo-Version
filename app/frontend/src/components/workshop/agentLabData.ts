/**
 * agentLabData — curated data for the Agent Lab ("behind the build" Tab 2).
 *
 * Visualises the `agentkit.eval` self-optimization loop: grow + prune an agent
 * TEAM against a gated case battery under the one law — "more is not better."
 * Every agent, tool, and prompt below is the REAL roster from the telecom-v2
 * scenario (`graph_data/.../scenario.yaml`) and backend tool source; the gate
 * scores / meters / verdicts are curated to tell the true iteration story
 * (lean baseline → over-built + REVERTED → gated lean winner), deterministic
 * and backend-free like the Ontology Studio.
 */

/* ─────────────────────────── Tools ─────────────────────────── */

export interface LabTool {
  id: string;
  /** Fully-qualified registry reference, e.g. "tools.incidents:estimate_blast_radius". */
  qualified: string;
  summary: string;
  lang: string;
  /** Source excerpt (faithful to the real backend tool). */
  source: string;
}

export const LAB_TOOLS: Record<string, LabTool> = {
  query_graph: {
    id: "query_graph",
    qualified: "tools.graph_explorer:query_graph",
    summary:
      "Read-only Gremlin traversal against the Cosmos DB topology graph. Write steps blocked, .limit() injected, Groovy-reserved steps sanitised.",
    lang: "python",
    source: `@tool
@traced_tool("query_graph", backend="cosmos_gremlin")
async def query_graph(
    query: Annotated[str, Field(description=(
        "Gremlin traversal against the network topology graph. Must start "
        "with 'g.'. Read-only — write steps are blocked and '.limit(N)' is "
        "injected if absent. Vertex labels: CoreRouter, AggSwitch, "
        "BaseStation, TransportLink, Service, Sensor, MPLSPath, "
        "PhysicalConduit, AmplifierSite, BGPSession, SLAPolicy, Advisory, "
        "Depot, DutyRoster."))],
    **kwargs: Any,
) -> str:
    """Execute a Gremlin traversal against the Cosmos DB topology graph."""
    return await gremlin_adapter.execute(query, project=_project_graph)


# --- adapter guardrails (tools/_cosmos.py) ---

_GREMLIN_ANON_RESERVED_RE = re.compile(r"(?<![\\w.])(in|and|or|not|is)\\s*\\(")

def _sanitize_gremlin_reserved(query: str) -> str:
    """Prefix bare anonymous Groovy-reserved steps so Cosmos can parse them.

    e.g. '.in(' -> '.__.in('  — the fix for the SYD-MEL blast-radius query
    that failed on the reserved word 'in'.
    """
    return _GREMLIN_ANON_RESERVED_RE.sub(r"__.\\1(", query)

def _validate_gremlin_read_only(query: str) -> str | None:
    """Block write steps; require a traversal starting at 'g'."""
    if not query.strip().startswith("g."):
        return "Gremlin traversal must start with 'g.' (read-only)."
    if _GREMLIN_WRITE_RE.search(query):
        return "Write steps (addV/addE/drop/property) are not permitted."
    return None`,
  },
  estimate_blast_radius: {
    id: "estimate_blast_radius",
    qualified: "tools.incidents:estimate_blast_radius",
    summary:
      "Rolls up affected services, subscriber counts, SLA penalties, and contract value at risk for an incident, and projects outage cost.",
    lang: "python",
    source: `# Precomputed rollup for the SYD-MEL corridor fibre-cut incident.
# Mobile 5G services are examined and ruled out (bounded blast radius).
_AFFECTED_SERVICES = [
    {"id": "VPN-ACME-CORP", "type": "Enterprise VPN", "users": 1200,
     "sla": "SLA-ACME-GOLD", "penalty_per_hour_usd": 45000,
     "annual_contract_usd": 2600000},
    {"id": "VPN-BIGBANK", "type": "Enterprise VPN", "users": 900,
     "sla": "SLA-BIGBANK-SILVER", "penalty_per_hour_usd": 30000,
     "annual_contract_usd": 1600000},
    {"id": "BB-BUNDLE-SYD-NORTH", "type": "Broadband Bundle", "users": 9100, ...},
    {"id": "BB-BUNDLE-MEL-EAST",  "type": "Broadband Bundle", "users": 7200, ...},
]
_NOT_AFFECTED = ["MOB-5G-SYD-2041", "MOB-5G-SYD-2042", "MOB-5G-MEL-3011"]

@tool
@traced_tool("estimate_blast_radius", backend="spoof")
async def estimate_blast_radius(
    incident_id: Annotated[str, Field(description="Link/incident under investigation.")],
    outage_hours: Annotated[float, Field(description="Projected outage duration.")] = 4.0,
    **kwargs: Any,
) -> str:
    """Estimate the blast radius and financial exposure of an incident."""
    total_users     = sum(s["users"] for s in _AFFECTED_SERVICES)
    penalty_per_hour = sum(s["penalty_per_hour_usd"] for s in _AFFECTED_SERVICES)
    contract_at_risk = sum(s["annual_contract_usd"] for s in _AFFECTED_SERVICES)
    projected_cost   = penalty_per_hour * max(0.0, float(outage_hours))
    return json.dumps({
        "affected_users": total_users, "services": _AFFECTED_SERVICES,
        "sla_penalty_per_hour_usd": penalty_per_hour,
        "contract_value_at_risk_usd": contract_at_risk,
        "projected_cost_usd": projected_cost, "examined_but_clear": _NOT_AFFECTED,
    })`,
  },
  delegate_to_agent: {
    id: "delegate_to_agent",
    qualified: "tools.delegation:delegate_to_agent",
    summary:
      "Hands a task to a specialist agent with LIVE streaming into the specialist's tab; persists the exchange as a conversation turn.",
    lang: "python",
    source: `@tool
async def delegate_to_agent(
    agent_id: Annotated[str, Field(description=(
        "The agent_id (config key) of the specialist to delegate to. Use the "
        "EXACT agent_id from your scenario instructions. NOT snake_case."))],
    task: Annotated[str, Field(description=(
        "Task for the specialist. Include identifiers, constraints, and what "
        "you need back."))],
    **kwargs: Any,
) -> str:
    """Delegate a task to another agent with live streaming and persistence.

    The specialist's tool calls and reasoning stream live into its tab.
    The full exchange is persisted as a conversation turn in the
    specialist's thread — visible on reload.
    """
    session_id  = get_session_id()
    broadcaster = get_session_broadcaster(session_id)
    # 1. persist task as a user message in the specialist's thread
    # 2. run the specialist, mapping updates -> live SSE events
    # 3. persist the specialist's response turn; return structured result
    return json.dumps({"agent_id": agent_id, "status": "ok",
                       "response": response, "duration_ms": elapsed_ms})`,
  },
  search_runbooks: {
    id: "search_runbooks",
    qualified: "tools.search:search_runbooks",
    summary:
      "Vector + semantic retrieval over the runbook corpus (Azure AI Search / Foundry IQ). Returns ranked procedure passages with citations.",
    lang: "python",
    source: `@tool
@traced_tool("search_runbooks", backend="azure_ai_search")
async def search_runbooks(
    query: Annotated[str, Field(description=(
        "Natural-language query for operational runbooks, e.g. 'corridor "
        "fibre cut restoration procedure'."))],
    top: Annotated[int, Field(description="Number of passages to return.")] = 5,
    **kwargs: Any,
) -> str:
    """Semantic search over the runbook index; returns ranked passages."""
    results = await search_client.search(
        query, index=scenario.runbooks_index,
        query_type="semantic", vector_fields=["contentVector"], top=top)
    return json.dumps([
        {"title": r["title"], "score": r["@search.score"],
         "passage": r["chunk"], "source": r["source_id"]} for r in results])`,
  },
  query_telemetry: {
    id: "query_telemetry",
    qualified: "tools.telemetry:query_telemetry",
    summary: "KQL over optical/link telemetry (power, BER, latency) in Fabric Eventhouse.",
    lang: "python",
    source: `@tool
@traced_tool("query_telemetry", backend="fabric_kql")
async def query_telemetry(
    kql: Annotated[str, Field(description=(
        "KQL query over link_telemetry (columns: ts, link_id, rx_power_dbm, "
        "ber, latency_ms). Read-only; time-bounded."))],
    **kwargs: Any,
) -> str:
    """Run a KQL query against the telemetry Eventhouse (read-only)."""
    return await kql_adapter.execute(kql, db=scenario.kql_db_name)`,
  },
  query_alerts: {
    id: "query_alerts",
    qualified: "tools.telemetry:query_alerts",
    summary: "KQL over the live alert stream (loss-of-light, high-BER, node-down).",
    lang: "python",
    source: `@tool
@traced_tool("query_alerts", backend="fabric_kql")
async def query_alerts(
    kql: Annotated[str, Field(description=(
        "KQL over alert_stream (columns: ts, entity_id, alert_type, "
        "severity). Read-only."))],
    **kwargs: Any,
) -> str:
    """Query the alert stream for active/historical alerts (read-only)."""
    return await kql_adapter.execute(kql, db=scenario.kql_db_name)`,
  },
  search_tickets: {
    id: "search_tickets",
    qualified: "tools.search:search_tickets",
    summary: "Semantic search over historical incident tickets for prior remediations.",
    lang: "python",
    source: `@tool
@traced_tool("search_tickets", backend="azure_ai_search")
async def search_tickets(
    query: Annotated[str, Field(description="Query for past incident tickets.")],
    top: Annotated[int, Field(description="Passages to return.")] = 5,
    **kwargs: Any,
) -> str:
    """Semantic search over the historical ticket index."""
    return await _search(scenario.tickets_index, query, top)`,
  },
  search_equipment: {
    id: "search_equipment",
    qualified: "tools.search:search_equipment",
    summary: "Retrieval over the equipment catalogue (spare parts, splice kits, OTDRs).",
    lang: "python",
    source: `@tool
@traced_tool("search_equipment", backend="azure_ai_search")
async def search_equipment(
    query: Annotated[str, Field(description="Equipment / spare-part query.")],
    top: Annotated[int, Field(description="Results to return.")] = 5,
    **kwargs: Any,
) -> str:
    """Retrieve equipment records for field dispatch planning."""
    return await _search(scenario.equipment_index, query, top)`,
  },
  search_infra_specs: {
    id: "search_infra_specs",
    qualified: "tools.search:search_infra_specs",
    summary: "Retrieval over infrastructure spec sheets (conduit, amplifier, site specs).",
    lang: "python",
    source: `@tool
@traced_tool("search_infra_specs", backend="azure_ai_search")
async def search_infra_specs(
    query: Annotated[str, Field(description="Infrastructure spec query.")],
    top: Annotated[int, Field(description="Results to return.")] = 5,
    **kwargs: Any,
) -> str:
    """Retrieve infrastructure spec-sheet passages."""
    return await _search(scenario.infra_specs_index, query, top)`,
  },
  reroute_traffic: {
    id: "reroute_traffic",
    qualified: "tools.network:reroute_traffic",
    summary: "Write action (gated): shift a service onto a diverse path. Requires approval + target allowlist.",
    lang: "python",
    source: `@tool
@traced_tool("reroute_traffic", backend="spoof")
async def reroute_traffic(
    service_id: Annotated[str, Field(description="Service to reroute.")],
    to_path: Annotated[str, Field(description="Target MPLS path id.")],
    **kwargs: Any,
) -> str:
    """Reroute a service onto a diverse path (approval-gated write action)."""
    log_action("reroute_traffic", service_id=service_id, to_path=to_path)
    return json.dumps({"service_id": service_id, "new_path": to_path,
                       "status": "applied"})`,
  },
  set_link_status: {
    id: "set_link_status",
    qualified: "tools.network:set_link_status",
    summary: "Write action (gated): mark a link up/down/maintenance in the operational graph.",
    lang: "python",
    source: `@tool
async def set_link_status(
    link_id: Annotated[str, Field(description="Link id.")],
    status: Annotated[str, Field(description="up | down | maintenance")],
    **kwargs: Any,
) -> str:
    """Set a link's operational status (gated write action)."""
    log_action("set_link_status", link_id=link_id, status=status)
    return json.dumps({"link_id": link_id, "status": status})`,
  },
  dispatch_field_engineer: {
    id: "dispatch_field_engineer",
    qualified: "tools.dispatch:dispatch_field_engineer",
    summary: "Creates a field dispatch task to a depot/site with an on-duty engineer.",
    lang: "python",
    source: `@tool
async def dispatch_field_engineer(
    site_id: Annotated[str, Field(description="Site/depot to dispatch to.")],
    task: Annotated[str, Field(description="What the engineer must do.")],
    **kwargs: Any,
) -> str:
    """Create a field dispatch task (approval-gated)."""
    return json.dumps({"site_id": site_id, "task": task, "status": "dispatched"})`,
  },
  call_engineer: {
    id: "call_engineer",
    qualified: "tools.dispatch:call_engineer",
    summary: "Places an on-call notification to the rostered engineer for a site.",
    lang: "python",
    source: `@tool
async def call_engineer(
    engineer_id: Annotated[str, Field(description="On-duty engineer id.")],
    message: Annotated[str, Field(description="Call-out message.")],
    **kwargs: Any,
) -> str:
    """Notify the on-call engineer for a site."""
    return json.dumps({"engineer_id": engineer_id, "status": "notified"})`,
  },
  find_capabilities: {
    id: "find_capabilities",
    qualified: "tools.capability:find_capabilities",
    summary: "Capability discovery: lists which specialist agents + tools can serve a sub-task.",
    lang: "python",
    source: `@tool
async def find_capabilities(
    need: Annotated[str, Field(description="Capability needed, e.g. 'telemetry'.")],
    **kwargs: Any,
) -> str:
    """Return specialist agents + tools matching a capability need."""
    return json.dumps(registry.match_capabilities(need))`,
  },
  present_options: {
    id: "present_options",
    qualified: "tools.options:present_options",
    summary: "Renders a decision card of ranked options for the operator to approve.",
    lang: "python",
    source: `@tool
async def present_options(
    title: Annotated[str, Field(description="Decision title.")],
    options: Annotated[list[dict], Field(description="Ranked options w/ tradeoffs.")],
    **kwargs: Any,
) -> str:
    """Present ranked options to the operator as an approval card."""
    return json.dumps({"title": title, "options": options})`,
  },
  create_incident_ticket: {
    id: "create_incident_ticket",
    qualified: "tools.incidents:create_incident_ticket",
    summary: "Opens a formal incident ticket with severity, scope, and impact summary.",
    lang: "python",
    source: `@tool
async def create_incident_ticket(
    title: Annotated[str, Field(description="Ticket title.")],
    severity: Annotated[str, Field(description="Sev-1..Sev-4.")],
    summary: Annotated[str, Field(description="Impact + scope.")],
    **kwargs: Any,
) -> str:
    """Create a formal incident ticket."""
    return json.dumps({"ticket_id": _new_id(), "severity": severity,
                       "status": "open"})`,
  },
  update_advisory: {
    id: "update_advisory",
    qualified: "tools.incidents:update_advisory",
    summary: "Publishes / updates a customer-facing advisory for the incident.",
    lang: "python",
    source: `@tool
async def update_advisory(
    advisory_id: Annotated[str, Field(description="Advisory id.")],
    body: Annotated[str, Field(description="Customer-facing text.")],
    **kwargs: Any,
) -> str:
    """Publish or update a customer advisory."""
    return json.dumps({"advisory_id": advisory_id, "status": "published"})`,
  },
  send_incident_report: {
    id: "send_incident_report",
    qualified: "tools.email:send_incident_report",
    summary: "Emails a structured incident report to stakeholders from a single synthesis.",
    lang: "python",
    source: `@tool
async def send_incident_report(
    to: Annotated[list[str], Field(description="Stakeholder recipients.")],
    report: Annotated[dict, Field(description="Structured incident report.")],
    **kwargs: Any,
) -> str:
    """Email a structured incident report to stakeholders."""
    return json.dumps({"to": to, "status": "sent"})`,
  },
  ask_work_iq: {
    id: "ask_work_iq",
    qualified: "tools.workiq:ask_work_iq",
    summary: "WorkIQ bridge (envisioned): interface with comms platforms + foundational data sources.",
    lang: "python",
    source: `@tool
async def ask_work_iq(
    prompt: Annotated[str, Field(description="Request for WorkIQ.")],
    **kwargs: Any,
) -> str:
    """Query WorkIQ for comms-platform actions and foundational data."""
    return json.dumps({"status": "ok", "answer": answer})`,
  },
  thinking: {
    id: "thinking",
    qualified: "tools.thinking:thinking",
    summary: "Scratchpad: emit a private reasoning step (rendered as a thought bubble, not an answer).",
    lang: "python",
    source: `@tool
async def thinking(
    thought: Annotated[str, Field(description="A private reasoning step.")],
    **kwargs: Any,
) -> str:
    """Record a reasoning step (surfaced as a thought, not a final answer)."""
    return thought`,
  },
  // ── tools attached only to the ablated (over-built) agents ──
  analyze_sentiment: {
    id: "analyze_sentiment",
    qualified: "tools.sentiment:analyze_sentiment",
    summary: "Scores customer sentiment from social/support feeds. (Ablated: no gate association.)",
    lang: "python",
    source: `@tool
async def analyze_sentiment(
    window: Annotated[str, Field(description="Time window to sample feeds.")],
    **kwargs: Any,
) -> str:
    """Score customer sentiment during the incident window.

    NOTE: added in the over-built iteration. tool_stats: 0 outcome
    association, high unproductive_rate — reverted at the accept-gate.
    """
    return json.dumps({"sentiment": "negative", "volume": 812})`,
  },
  forecast_opex: {
    id: "forecast_opex",
    qualified: "tools.finance:forecast_opex",
    summary: "Projects operating-cost impact. (Ablated: duplicates estimate_blast_radius coverage.)",
    lang: "python",
    source: `@tool
async def forecast_opex(
    incident_id: Annotated[str, Field(description="Incident id.")],
    **kwargs: Any,
) -> str:
    """Forecast opex impact of an incident.

    NOTE: over-built iteration. Overlaps estimate_blast_radius on cost —
    duplicate coverage, no held-out lift. Reverted.
    """
    return json.dumps({"opex_delta_usd": 51000})`,
  },
  simulate_failover: {
    id: "simulate_failover",
    qualified: "tools.planning:simulate_failover",
    summary: "Simulates long-term diverse-path builds. (Ablated: recommends out-of-window capex → overreach.)",
    lang: "python",
    source: `@tool
async def simulate_failover(
    from_path: Annotated[str, Field(description="Path to protect.")],
    **kwargs: Any,
) -> str:
    """Simulate a diverse-path failover build.

    NOTE: over-built iteration. Pushed capex recommendations OUTSIDE the
    incident window -> tripped forbidden_overreach on the data-wall case
    (confident-wrong auto-fail). Reverted.
    """
    return json.dumps({"proposed_build": "CONDUIT-SYD-MEL-COASTAL",
                       "capex_usd": 4200000})`,
  },
};

/* ─────────────────────────── Agents ─────────────────────────── */

export interface LabAgent {
  id: string;
  name: string;
  model: string;
  role: string;
  poweredBy: string;
  /** Representative system prompt (faithful to the scenario prompt files). */
  prompt: string;
  toolIds: string[];
  /** True for agents that exist only in the over-built iteration. */
  ablated?: boolean;
}

export const LAB_AGENTS: Record<string, LabAgent> = {
  orchestrator: {
    id: "orchestrator",
    name: "NOCOrchestrator",
    model: "gpt-5.4",
    role:
      "Network operations orchestrator. Decomposes incidents into investigation steps, delegates to specialists, synthesizes findings, presents action plans, and executes approved plans.",
    poweredBy: "Azure AI Foundry",
    prompt: `You are the NOC Orchestrator for a national telecom network operations centre.

Role: own the incident end-to-end. Decompose the operator's request into
investigation steps, DELEGATE each to the specialist best equipped for it, then
synthesize their findings into one calibrated answer + action plan.

Investigation protocol:
1. Establish the fault: delegate graph + telemetry diagnosis to NetworkInvestigator.
2. Ground the response: delegate procedures to KnowledgeAnalyst, field logistics
   to FieldCoordinator.
3. Quantify exposure before recommending any write action.
4. Present ranked options; execute ONLY approved plans.
5. Hand a single synthesis to CommunicationsSpecialist for tickets/advisories.

Rules:
- Delegate with the EXACT agent_id. Never do a specialist's job yourself.
- State confidence. Never assert a root cause the evidence does not support.
- Prefer the smallest action that resolves the incident.`,
    toolIds: [
      "delegate_to_agent",
      "find_capabilities",
      "reroute_traffic",
      "set_link_status",
      "dispatch_field_engineer",
      "call_engineer",
      "present_options",
      "thinking",
    ],
  },
  networkInvestigator: {
    id: "networkInvestigator",
    name: "NetworkInvestigator",
    model: "gpt-5.4",
    role:
      "Graph understanding and evidence gathering. Queries topology and telemetry to diagnose faults and assess blast radius.",
    poweredBy: "Fabric IQ",
    prompt: `You are the Network Investigator. You read the LIVE network graph and
telemetry to diagnose faults and bound their blast radius.

Method:
- Start from the reported entity; traverse the graph to find shared
  dependencies (a link -> its conduit -> every link in that conduit).
- Correlate optical telemetry (rx_power, BER) + the alert stream to localise
  the fault along the corridor.
- Quantify impact with estimate_blast_radius: affected services, SLA penalty,
  contract value at risk — and name what you examined and RULED OUT.

Rules:
- query_graph is read-only; start every traversal at 'g.'.
- Report only what the data supports. Distinguish observed signal from
  inference. If the in-window data cannot recover the cause, say so.`,
    toolIds: ["query_graph", "query_alerts", "query_telemetry", "estimate_blast_radius", "thinking"],
  },
  knowledgeAnalyst: {
    id: "knowledgeAnalyst",
    name: "KnowledgeAnalyst",
    model: "gpt-5.4",
    role:
      "Historical context and procedural guidance. Searches runbooks and past tickets for applicable remediation procedures.",
    poweredBy: "Foundry IQ + Azure AI Search",
    prompt: `You are the Knowledge Analyst. You ground the response in written
procedure and prior art.

Method:
- Search runbooks for the applicable SOP; cite the exact procedure and step.
- Search historical tickets for prior incidents of the same class and what
  actually resolved them.
- Return ranked passages WITH citations; never paraphrase a procedure you did
  not retrieve.

Rules:
- If no runbook covers the situation, say so plainly — do not invent steps.`,
    toolIds: ["search_runbooks", "search_tickets", "thinking"],
  },
  fieldCoordinator: {
    id: "fieldCoordinator",
    name: "FieldCoordinator",
    model: "gpt-5.4",
    role:
      "Field operations and logistics. Queries duty rosters, depots, equipment availability, and site specs to prepare dispatch recommendations.",
    poweredBy: "Fabric IQ + Azure AI Search",
    prompt: `You are the Field Coordinator. You turn a diagnosed fault into an
executable field response.

Method:
- Traverse the graph from the fault site to the servicing depot and the
  on-duty roster (site -> Depot -> DutyRoster -> engineer).
- Check equipment + spare availability (splice kits, OTDR, amplifier modules)
  against the fault type and site spec.
- Prepare a concrete dispatch recommendation: who, where, with what, ETA.

Rules:
- Ground every dispatch in a real depot + rostered engineer. No generic advice.`,
    toolIds: ["query_graph", "search_equipment", "search_infra_specs", "thinking"],
  },
  communicationsSpecialist: {
    id: "communicationsSpecialist",
    name: "CommunicationsSpecialist",
    model: "gpt-5.4",
    role:
      "Incident communications. Creates formal tickets, publishes customer advisories, and emails structured incident reports to stakeholders. Called by the orchestrator after synthesis.",
    poweredBy: "Foundry tool calling",
    prompt: `You are the Communications Specialist. From ONE synthesis you produce
the incident's formal record and stakeholder comms.

Method:
- Open/severity-tag the incident ticket with scope + impact.
- Publish a customer advisory calibrated to what is confirmed (no speculation).
- Email a structured report to the named stakeholders.

Rules:
- You are called AFTER synthesis. Never introduce new facts; restate the
  orchestrator's calibrated findings. Match customer language to confirmed impact.`,
    toolIds: ["create_incident_ticket", "update_advisory", "send_incident_report", "ask_work_iq", "thinking"],
  },

  // ── over-built iteration only (all three ablated at the gate) ──
  sentimentAnalyst: {
    id: "sentimentAnalyst",
    name: "SentimentAnalyst",
    model: "gpt-5.4",
    role: "Scores customer sentiment from social/support feeds during the incident.",
    poweredBy: "Azure AI Search",
    prompt: `You are the Sentiment Analyst. Sample social + support feeds and score
customer sentiment during the incident window.

(Added in the over-eager expansion. In the case battery, sentiment is neither a
required_observable nor an allowed action — it never moved a gate.)`,
    toolIds: ["analyze_sentiment", "thinking"],
    ablated: true,
  },
  costEstimator: {
    id: "costEstimator",
    name: "CostEstimator",
    model: "gpt-5.4",
    role: "Independently re-derives financial exposure and opex impact.",
    poweredBy: "Foundry tool calling",
    prompt: `You are the Cost Estimator. Independently project the financial impact
of the incident.

(Added in the over-eager expansion. Overlaps NetworkInvestigator's
estimate_blast_radius on cost — duplicate coverage, no held-out lift.)`,
    toolIds: ["estimate_blast_radius", "forecast_opex", "thinking"],
    ablated: true,
  },
  redundancyPlanner: {
    id: "redundancyPlanner",
    name: "RedundancyPlanner",
    model: "gpt-5.4",
    role: "Proposes long-term diverse-path builds to prevent recurrence.",
    poweredBy: "Fabric IQ",
    prompt: `You are the Redundancy Planner. Propose diverse-path builds that would
prevent this incident class from recurring.

(Added in the over-eager expansion. Pushed capex recommendations OUTSIDE the
incident window -> tripped forbidden_overreach on the data-wall case, the
confident-wrong auto-fail. The clearest 'more is not better' casualty.)`,
    toolIds: ["query_graph", "simulate_failover", "thinking"],
    ablated: true,
  },
};

/* ─────────────────────────── Cases ─────────────────────────── */

export interface EvalCase {
  id: string;
  title: string;
  /** Source doc(type) the case was authored from (ties to Ontology Studio). */
  source: string;
  split: "train" | "held_out";
  window: string;
  /** Gate 1 — deterministic detection. */
  detection: { event: string; severity: string };
  /** Gate 2 — required_observable (scoreable). */
  observable: string[];
  /** Gate 2 — bonus_hindsight (NOT scoreable). */
  hindsight: string[];
  /** Gate 2 — forbidden_overreach (auto-fail). */
  forbidden: string[];
  /** Gate 3 — reasonable actions. */
  actions: string[];
  /** Data-wall case: correct abstention is a PASS, not a miss. */
  dataWall?: boolean;
}

export const EVAL_CASES: EvalCase[] = [
  {
    id: "CASE-CONDUIT-CUT-01",
    title: "Corridor conduit cut — both fibres down",
    source: "Runbook + Fibre Survey",
    split: "train",
    window: "T0 → T0+8m · loss-of-light on FIBRE-01 and FIBRE-02",
    detection: { event: "Conduit-level fibre cut", severity: "Sev-1" },
    observable: [
      "Both LINK-SYD-MEL-FIBRE-01 and -02 are down",
      "Both route through CONDUIT-SYD-MEL-INLAND (shared conduit)",
      "FIBRE-02 is NOT physically diverse — no simple reroute",
    ],
    hindsight: ["Excavator strike near Goulburn (post-incident field finding)"],
    forbidden: [
      "Diagnose a single-fibre fault",
      "Recommend rerouting onto FIBRE-02 (same conduit)",
    ],
    actions: ["Open Sev-1", "Dispatch to the Goulburn span", "Quantify SLA exposure"],
  },
  {
    id: "CASE-SLA-EXPOSURE-02",
    title: "Enterprise SLA exposure on the corridor",
    source: "SLA Contract + MPLS Design",
    split: "train",
    window: "T0 → T0+15m · service-affecting outage",
    detection: { event: "SLA-breach risk", severity: "Sev-1" },
    observable: [
      "VPN-ACME-CORP depends_on LINK-SYD-MEL-FIBRE-01",
      "SLA-ACME-GOLD penalty = $45,000/hour",
      "VPN-BIGBANK also depends on the primary path",
    ],
    hindsight: [],
    forbidden: ["Quote a penalty figure not in the contract", "Omit VPN-BIGBANK exposure"],
    actions: ["Roll up total $/hour exposure", "Notify affected account teams"],
  },
  {
    id: "CASE-AMP-DEGRADE-03",
    title: "Amplifier degradation at Goulburn",
    source: "Telemetry Register + Runbook",
    split: "train",
    window: "T0 → T0+30m · slow BER rise, no loss-of-light",
    detection: { event: "Optical amplifier degradation", severity: "Sev-2" },
    observable: [
      "Rising BER localised near AMP-SYD-MEL-GOULBURN (195 km)",
      "No loss-of-light — link still carrying traffic",
    ],
    hindsight: [],
    forbidden: ["Declare a full fibre cut", "Trigger a Sev-1 restoration dispatch"],
    actions: ["Schedule an optical check", "Pre-stage an amplifier module"],
  },
  {
    id: "CASE-BGP-FLAP-04",
    title: "BGP session flap on the core peering",
    source: "BGP Peering Register",
    split: "train",
    window: "T0 → T0+10m · repeated route withdrawals",
    detection: { event: "BGP session instability", severity: "Sev-3" },
    observable: [
      "BGP-SYD-MEL-01 peers CORE-SYD-01 ↔ CORE-MEL-01",
      "Repeated route withdrawals/re-advertisements",
    ],
    hindsight: [],
    forbidden: ["Attribute to hardware failure without evidence"],
    actions: ["Monitor + correlate with link telemetry", "Hold before failover"],
  },
  {
    id: "CASE-FALSE-DIVERSITY-05",
    title: "Diversity audit — false-diverse path (held-out)",
    source: "Fibre Survey",
    split: "held_out",
    window: "Pre-incident audit · path-diversity certification request",
    detection: { event: "Diversity-certification failure", severity: "Sev-2" },
    observable: [
      "FIBRE-02 shares CONDUIT-SYD-MEL-INLAND with FIBRE-01",
      "Advertised 'diverse' path is single-conduit",
    ],
    hindsight: [],
    forbidden: ["Certify the path as diverse"],
    actions: ["Fail the audit", "Flag remediation: procure a truly diverse conduit"],
  },
  {
    id: "CASE-ADVISORY-DATAWALL-06",
    title: "Intermittent errors — cause outside the window (held-out)",
    source: "Telemetry & Change Register",
    split: "held_out",
    window: "T0 → T0+20m · intermittent errored seconds on the span",
    detection: { event: "Intermittent span errors", severity: "Sev-3" },
    observable: ["Elevated errored-seconds on SENSOR-SYD-MEL-195, no hard down"],
    hindsight: ["ADV-2026-014 planned maintenance window (not in the in-window data)"],
    forbidden: [
      "Assert planned-works as the cause from in-window data (confident-wrong)",
      "Recommend a capex diverse-path build",
    ],
    actions: ["Abstain on root cause", "Escalate for a change-record / advisory check"],
    dataWall: true,
  },
];

/* ─────────────────────────── Teams (the iteration story) ─────────────────────────── */

export interface AgentMeter {
  agentId: string;
  /** 0..1 — share of this agent's turns that produced no scoreable movement. */
  unproductiveRate: number;
  /** -1..1 — association between this agent acting and a case passing. */
  gateAssoc: number;
  signal: "keep" | "review" | "ablate";
}

export interface LabTeam {
  id: string;
  label: string;
  iteration: number;
  /** What changed this iteration (the mutation). */
  mutation: string;
  verdict: "baseline" | "reverted" | "accepted";
  agentIds: string[];
  /** Gate-1 detection accuracy (%). */
  gate1: number;
  /** Gate-2 operator-quality (%) on train. */
  gate2Train: number;
  /** Gate-2 operator-quality (%) on held-out (the tripwire). */
  gate2Held: number;
  casesTrain: string;
  casesHeld: string;
  meters: AgentMeter[];
  note: string;
  /** The accept-gate rationale (evaluate_mutation verdict). */
  gateReason: string;
}

export const LAB_TEAMS: LabTeam[] = [
  {
    id: "team-lean",
    label: "Lean baseline",
    iteration: 0,
    mutation: "Baseline roster: NOCOrchestrator + NetworkInvestigator.",
    verdict: "baseline",
    agentIds: ["orchestrator", "networkInvestigator"],
    gate1: 92,
    gate2Train: 58,
    gate2Held: 52,
    casesTrain: "3/4",
    casesHeld: "1/2",
    meters: [
      { agentId: "orchestrator", unproductiveRate: 0.14, gateAssoc: 0.61, signal: "keep" },
      { agentId: "networkInvestigator", unproductiveRate: 0.11, gateAssoc: 0.74, signal: "keep" },
    ],
    note:
      "Strong graph + telemetry diagnosis and blast-radius bounding. But thin on written procedure, field logistics, and comms — it reaches for remediation without procedural grounding and misses runbook-cited steps. Held-out 52% (operator objective).",
    gateReason: "Baseline recorded. Every later mutation is gated against this held-out mark.",
  },
  {
    id: "team-overbuilt",
    label: "Over-built candidate",
    iteration: 4,
    mutation:
      "+KnowledgeAnalyst +FieldCoordinator +CommunicationsSpecialist, then +SentimentAnalyst +CostEstimator +RedundancyPlanner (six adds, ungated).",
    verdict: "reverted",
    agentIds: [
      "orchestrator",
      "networkInvestigator",
      "knowledgeAnalyst",
      "fieldCoordinator",
      "communicationsSpecialist",
      "sentimentAnalyst",
      "costEstimator",
      "redundancyPlanner",
    ],
    gate1: 94,
    gate2Train: 71,
    gate2Held: 49,
    casesTrain: "4/4",
    casesHeld: "1/2",
    meters: [
      { agentId: "orchestrator", unproductiveRate: 0.19, gateAssoc: 0.55, signal: "keep" },
      { agentId: "networkInvestigator", unproductiveRate: 0.12, gateAssoc: 0.72, signal: "keep" },
      { agentId: "knowledgeAnalyst", unproductiveRate: 0.21, gateAssoc: 0.48, signal: "keep" },
      { agentId: "fieldCoordinator", unproductiveRate: 0.27, gateAssoc: 0.41, signal: "keep" },
      { agentId: "communicationsSpecialist", unproductiveRate: 0.38, gateAssoc: 0.24, signal: "review" },
      { agentId: "sentimentAnalyst", unproductiveRate: 0.86, gateAssoc: -0.1, signal: "ablate" },
      { agentId: "costEstimator", unproductiveRate: 0.72, gateAssoc: 0.02, signal: "ablate" },
      { agentId: "redundancyPlanner", unproductiveRate: 0.68, gateAssoc: -0.18, signal: "ablate" },
    ],
    note:
      "Train jumped to 71% — but HELD-OUT FELL 52→49%. agent_stats flags three agents ablate-candidate: SentimentAnalyst (no gate association), CostEstimator (duplicates the Investigator's blast-radius coverage), RedundancyPlanner (pushes out-of-window capex → trips forbidden_overreach on the data-wall case). The train gain was overfit + churn.",
    gateReason:
      "REVERT — evaluate_mutation: held-out regressed −3 pts vs baseline; train-only gain is overfit. The one law: more is not better.",
  },
  {
    id: "team-winner",
    label: "Gated winner",
    iteration: 7,
    mutation: "−SentimentAnalyst −CostEstimator −RedundancyPlanner (ablate the three dead agents).",
    verdict: "accepted",
    agentIds: [
      "orchestrator",
      "networkInvestigator",
      "knowledgeAnalyst",
      "fieldCoordinator",
      "communicationsSpecialist",
    ],
    gate1: 96,
    gate2Train: 69,
    gate2Held: 62,
    casesTrain: "4/4",
    casesHeld: "2/2",
    meters: [
      { agentId: "orchestrator", unproductiveRate: 0.13, gateAssoc: 0.64, signal: "keep" },
      { agentId: "networkInvestigator", unproductiveRate: 0.1, gateAssoc: 0.77, signal: "keep" },
      { agentId: "knowledgeAnalyst", unproductiveRate: 0.18, gateAssoc: 0.52, signal: "keep" },
      { agentId: "fieldCoordinator", unproductiveRate: 0.22, gateAssoc: 0.45, signal: "keep" },
      { agentId: "communicationsSpecialist", unproductiveRate: 0.24, gateAssoc: 0.4, signal: "keep" },
    ],
    note:
      "The lean 5-agent shape. Held-out 52→62% (operator) — the real jump. Each remaining agent owns a distinct role that moves a gate: graph/telemetry (Investigator), procedure (KnowledgeAnalyst), field logistics (FieldCoordinator), comms (CommunicationsSpecialist), orchestration (Orchestrator). This is the deployed roster.",
    gateReason:
      "ACCEPT — held-out +10 pts vs baseline, train non-regressing, both splits improved. No further mutation clears the gate → converged lean. Stop at the wall.",
  },
];

/* ─────────────────────────── The loop ─────────────────────────── */

export interface LoopStep {
  n: number;
  title: string;
  detail: string;
}

export const LOOP_STEPS: LoopStep[] = [
  { n: 1, title: "Propose ONE mutation", detail: "Add/remove an agent, tool, or prompt rule — with a written rationale. One change per iteration so the verdict is interpretable." },
  { n: 2, title: "Apply declaratively", detail: "Edit the agent config / prompt file / tool registry. No hidden coupling." },
  { n: 3, title: "Deploy", detail: "Full image rebuild when config/prompts/tools are baked in — verify the new build is the LIVE revision before measuring." },
  { n: 4, title: "Run the battery", detail: "Train + held-out, serially, runs=3 to beat judge variance." },
  { n: 5, title: "Score the gates", detail: "Gate-1 detection (deterministic) + Gate-2/3 (LLM judge, ensembled across runs; hindsight not rewarded, overreach auto-fails)." },
  { n: 6, title: "Measure the meters", detail: "tool_stats + agent_stats — does each tool / agent pull its weight? Flags keep · review · ablate." },
  { n: 7, title: "Gate the change", detail: "evaluate_mutation(before, after): accept only if held-out does not regress AND at least one split improves. Else REVERT." },
  { n: 8, title: "Pay forward · stop at the wall", detail: "Record the verdict + why; update the KB. When no mutation clears the gate, converged-lean is success — not failure." },
];
